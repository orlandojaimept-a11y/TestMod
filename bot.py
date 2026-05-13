"""
bot.py — Loja Digital  [hardened v4]

Melhorias vs v3 (bot-7.py):
  - Admins geridos por DB (tabela `admins`) em vez de variável de ambiente.
  - Primeiro utilizador a fazer /start é automaticamente promovido a admin
    (bootstrap único — só funciona se a tabela admins estiver vazia).
  - _is_admin() agora consulta a DB de forma assíncrona.
  - Novos comandos admin: /addadmin <id>, /rmadmin <id>, /admins
  - ADMIN_TELEGRAM_ID no .env continua a funcionar como seed inicial (opcional).
"""

import os
import json
import logging
import time
import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from db import (
    init_db,
    get_products,
    get_product,
    save_order,
    get_order_by_payment,
    mark_paid,
    list_orders,
    add_product,
    remove_product,
    is_admin,
    promote_first_user,
    add_admin,
    remove_admin,
    list_admins,
)
from payments import create_payment, verify_ipn_signature
from i18n import (
    get_lang, t,
    make_main_kb, make_admin_kb,
    BTN_PRODUCTS_RE, BTN_HELP_RE, BTN_BOTMAKER_RE,
    BTN_ORDERS_RE, BTN_ADD_RE, BTN_REMOVE_RE,
)

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

BOT_TOKEN    = os.environ["BOT_TOKEN"]
WEBHOOK_URL  = os.environ["WEBHOOK_URL"]
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"

ptb_app = Application.builder().token(BOT_TOKEN).updater(None).build()


# ── Rate limiter ──────────────────────────────────────────────────────────────

_RATE_WINDOW  = 60
_RATE_MAX     = 5
_PURGE_EVERY  = 300
_rate_buckets: dict[int, list[float]] = defaultdict(list)
_last_purge   = time.monotonic()

def _check_rate(user_id: int) -> bool:
    global _last_purge
    now = time.monotonic()
    if now - _last_purge > _PURGE_EVERY:
        expired = [uid for uid, ts in _rate_buckets.items()
                   if all(now - t > _RATE_WINDOW for t in ts)]
        for uid in expired:
            del _rate_buckets[uid]
        _last_purge = now
    _rate_buckets[user_id] = [t for t in _rate_buckets[user_id] if now - t < _RATE_WINDOW]
    if len(_rate_buckets[user_id]) >= _RATE_MAX:
        return False
    _rate_buckets[user_id].append(now)
    return True


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _is_admin(update: Update) -> bool:
    """Verifica admin via DB."""
    return await is_admin(update.effective_user.id)

async def _kb(update: Update):
    lang = get_lang(update)
    return make_admin_kb(lang) if await _is_admin(update) else make_main_kb(lang)

async def _reply(update: Update, text: str, **kwargs):
    try:
        await update.message.reply_text(text, **kwargs)
    except TelegramError as e:
        log.error(f"Erro ao enviar mensagem para uid={update.effective_user.id}: {e}")


# ── Global error handler ──────────────────────────────────────────────────────

async def error_handler(update: object, context) -> None:
    log.error("Exceção não tratada no handler PTB:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        lang = get_lang(update)
        try:
            await update.message.reply_text(t(lang, "err_generic"))
        except Exception:
            pass

ptb_app.add_error_handler(error_handler)


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()          # ← garante que a tabela admins existe
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.bot.set_webhook(
        url=f"{WEBHOOK_URL}{WEBHOOK_PATH}",
        allowed_updates=Update.ALL_TYPES,
    )
    yield
    await ptb_app.bot.delete_webhook()
    await ptb_app.stop()
    await ptb_app.shutdown()

api = FastAPI(lifespan=lifespan)


@api.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    try:
        payload = await request.json()
        update  = Update.de_json(payload, ptb_app.bot)
        await ptb_app.process_update(update)
    except json.JSONDecodeError:
        log.warning("Webhook: payload não é JSON válido.")
        return Response(status_code=400)
    except Exception as e:
        log.error(f"Webhook: erro inesperado ao processar update: {e}", exc_info=True)
    return Response(status_code=200)


@api.get("/health")
async def health():
    return {"status": "ok"}


# ── IPN ───────────────────────────────────────────────────────────────────────

@api.post("/ipn")
async def nowpayments_ipn(request: Request):
    sig  = request.headers.get("x-nowpayments-sig", "")
    body = await request.body()

    if not verify_ipn_signature(body, sig):
        log.warning("IPN rejeitado: assinatura inválida.")
        return Response(status_code=401)

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        log.error("IPN: body não é JSON válido.")
        return Response(status_code=400)

    payment_id     = str(data.get("payment_id", "")).strip()
    payment_status = str(data.get("payment_status", "")).strip()

    if payment_status not in ("finished", "confirmed"):
        return Response(status_code=200)

    if not payment_id:
        log.error("IPN: payment_id ausente ou vazio.")
        return Response(status_code=400)

    if len(payment_id) > 256:
        log.warning("IPN: payment_id suspeito (demasiado longo).")
        return Response(status_code=400)

    try:
        order = await get_order_by_payment(payment_id)
    except Exception as e:
        log.error(f"IPN: erro ao consultar pedido '{payment_id[:12]}…': {e}")
        return Response(status_code=500)

    if not order:
        log.warning(f"IPN: pedido não encontrado para payment_id={payment_id[:12]}…")
        return Response(status_code=200)

    if order["status"] == "paid":
        log.info(f"IPN: pedido {payment_id[:12]}… já estava pago. Ignorado.")
        return Response(status_code=200)

    try:
        await mark_paid(payment_id)
    except Exception as e:
        log.error(f"IPN: erro ao marcar pedido como pago: {e}")
        return Response(status_code=500)

    try:
        product = await get_product(order["product_id"])
    except Exception as e:
        log.error(f"IPN: erro ao obter produto '{order['product_id']}': {e}")
        return Response(status_code=500)

    if product:
        try:
            await ptb_app.bot.send_message(
                chat_id=int(order["user_id"]),
                text=t("en", "payment_confirmed",
                       name=product["name"],
                       link=product["download_link"]),
            )
        except TelegramError as e:
            log.warning(f"IPN: não foi possível enviar mensagem ao utilizador {order['user_id']}: {e}")
        except Exception as e:
            log.error(f"IPN: erro inesperado ao enviar mensagem: {e}")

    return Response(status_code=200)


# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx):
    lang    = get_lang(update)
    user_id = update.effective_user.id

    # Bootstrap: promove o primeiro utilizador a admin (só funciona uma vez)
    promoted = await promote_first_user(user_id)
    if promoted:
        log.warning(f"Bootstrap admin: user_id={user_id} (@{update.effective_user.username})")
        try:
            await update.message.reply_text(
                "👑 Foste promovido a administrador (primeiro utilizador do bot).\n"
                "Usa /admins para gerir administradores."
            )
        except TelegramError:
            pass

    await _reply(update, t(lang, "start"), reply_markup=await _kb(update))


# ── /produtos ─────────────────────────────────────────────────────────────────

async def cmd_produtos(update: Update, ctx):
    lang = get_lang(update)
    try:
        products = await get_products()
    except Exception as e:
        log.error(f"cmd_produtos: {e}")
        await _reply(update, t(lang, "err_generic"))
        return

    if not products:
        await _reply(update, t(lang, "products_empty"))
        return

    lines = [
        f"• {p['name']} — ${p['price_usd']:.2f}\n  👉 /comprar_{p['id']}"
        for p in products
    ]
    await _reply(
        update,
        t(lang, "products_header") + "\n\n" + "\n\n".join(lines),
        reply_markup=await _kb(update),
    )


# ── /comprar_<id> ─────────────────────────────────────────────────────────────

async def cmd_comprar(update: Update, ctx):
    lang = get_lang(update)
    uid  = update.effective_user.id

    if not _check_rate(uid):
        await _reply(update, t(lang, "err_rate_limit"))
        log.warning(f"Rate limit: user_id={uid}")
        return

    parts = update.message.text.strip().split("_", 1)
    if len(parts) < 2 or not parts[1].strip():
        await _reply(update, t(lang, "err_product_invalid"))
        return

    pid = parts[1].strip()
    if not pid.replace("-", "").isalnum() or len(pid) > 128:
        await _reply(update, t(lang, "err_product_invalid"))
        return

    try:
        p = await get_product(pid)
    except ValueError:
        await _reply(update, t(lang, "err_product_invalid"))
        return
    except Exception as e:
        log.error(f"cmd_comprar: get_product('{pid}'): {e}")
        await _reply(update, t(lang, "err_generic"))
        return

    if not p:
        await _reply(update, t(lang, "err_product_notfound"))
        return

    try:
        payment = await create_payment(p, uid)
    except Exception as e:
        log.error(f"cmd_comprar: create_payment: {e}")
        await _reply(update, t(lang, "err_payment"))
        return

    try:
        await save_order(uid, pid, payment["payment_id"], payment["pay_amount"], payment["pay_currency"])
    except Exception as e:
        log.error(f"cmd_comprar: save_order: {e}")
        await _reply(
            update,
            t(lang, "err_order_save",
              amount=payment.get("pay_amount", "—"),
              currency=payment.get("pay_currency", "—").upper(),
              address=payment.get("pay_address", "—")),
            reply_markup=await _kb(update),
        )
        return

    await _reply(
        update,
        t(lang, "order_created",
          name=p["name"],
          amount=payment.get("pay_amount", "—"),
          currency=payment.get("pay_currency", "—").upper(),
          address=payment.get("pay_address", "—")),
        reply_markup=await _kb(update),
    )


# ── /ajuda ────────────────────────────────────────────────────────────────────

async def cmd_ajuda(update: Update, ctx):
    lang = get_lang(update)
    await _reply(update, t(lang, "help"), reply_markup=await _kb(update))


# ── /botmaker ─────────────────────────────────────────────────────────────────

async def cmd_botmaker(update: Update, ctx):
    lang = get_lang(update)
    await _reply(update, t(lang, "botmaker"), reply_markup=await _kb(update))


# ── Admin: /pedidos ───────────────────────────────────────────────────────────

async def cmd_pedidos(update: Update, ctx):
    lang = get_lang(update)
    if not await _is_admin(update):
        await _reply(update, t(lang, "err_access_denied"))
        return

    try:
        orders = await list_orders(limit=20)
    except Exception as e:
        log.error(f"cmd_pedidos: {e}")
        await _reply(update, t(lang, "err_generic"))
        return

    if not orders:
        await _reply(update, "Nenhum pedido ainda.")
        return

    lines = [
        f"• {o['payment_id'][:12]}… | {o['status']} | {o['amount']} {o['currency']} | uid:{o['user_id']}"
        for o in orders
    ]
    body = "\n".join(lines)
    if len(body) > 3800:
        body = body[:3800] + "\n…"

    await _reply(
        update,
        f"📋 Últimos {len(orders)} pedidos:\n\n{body}",
        reply_markup=make_admin_kb(lang),
    )


# ── Admin: /addproduto ────────────────────────────────────────────────────────

async def cmd_addproduto(update: Update, ctx):
    lang = get_lang(update)
    if not await _is_admin(update):
        await _reply(update, t(lang, "err_access_denied"))
        return

    try:
        raw   = update.message.text.split(" ", 1)[1]
        parts = [x.strip() for x in raw.split("|")]
        if len(parts) != 5:
            raise ValueError("Número de campos inválido")
        nome, desc, preco, moeda, link = parts
        preco = float(preco.replace(",", "."))
        if preco <= 0:
            raise ValueError("Preço deve ser positivo")
        if not link.startswith("http"):
            raise ValueError("Link deve começar com http")
    except (IndexError, ValueError) as e:
        await _reply(
            update,
            f"❌ Formato inválido: {e}\n\n"
            "Uso:\n/addproduto nome | descrição | preço | moeda | link\n\n"
            "Exemplo:\n/addproduto Curso Python | Do zero ao avançado | 19.99 | BNB | https://exemplo.com/ficheiro.zip",
            reply_markup=make_admin_kb(lang),
        )
        return

    try:
        await add_product(nome, desc, preco, moeda, link)
    except ValueError as e:
        await _reply(update, f"❌ Dados inválidos: {e}", reply_markup=make_admin_kb(lang))
        return
    except Exception as e:
        log.error(f"cmd_addproduto: add_product: {e}")
        await _reply(update, t(lang, "err_generic"), reply_markup=make_admin_kb(lang))
        return

    await _reply(update, f"✅ Produto '{nome}' adicionado!", reply_markup=make_admin_kb(lang))


# ── Admin: /rmproduto ─────────────────────────────────────────────────────────

async def cmd_rmproduto(update: Update, ctx):
    lang = get_lang(update)
    if not await _is_admin(update):
        await _reply(update, t(lang, "err_access_denied"))
        return

    parts = update.message.text.strip().split(" ", 1)

    if len(parts) < 2 or not parts[1].strip():
        try:
            products = await get_products()
        except Exception as e:
            log.error(f"cmd_rmproduto: get_products: {e}")
            await _reply(update, t(lang, "err_generic"), reply_markup=make_admin_kb(lang))
            return

        if not products:
            await _reply(update, "Nenhum produto.", reply_markup=make_admin_kb(lang))
            return

        lines = [f"• {p['name']}\n  /rmproduto {p['id']}" for p in products]
        await _reply(
            update,
            "Qual produto remover?\n\n" + "\n\n".join(lines),
            reply_markup=make_admin_kb(lang),
        )
        return

    pid = parts[1].strip()
    try:
        await remove_product(pid)
    except ValueError as e:
        await _reply(update, f"❌ ID inválido: {e}", reply_markup=make_admin_kb(lang))
        return
    except Exception as e:
        log.error(f"cmd_rmproduto: remove_product('{pid}'): {e}")
        await _reply(update, t(lang, "err_generic"), reply_markup=make_admin_kb(lang))
        return

    await _reply(update, "✅ Produto desativado.", reply_markup=make_admin_kb(lang))


# ── Admin: /addadmin <user_id> ────────────────────────────────────────────────

async def cmd_addadmin(update: Update, ctx):
    lang = get_lang(update)
    if not await _is_admin(update):
        await _reply(update, t(lang, "err_access_denied"))
        return

    parts = update.message.text.strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await _reply(update, "Uso: /addadmin <telegram_user_id>")
        return

    new_id = int(parts[1])
    try:
        await add_admin(new_id, update.effective_user.id)
    except ValueError as e:
        await _reply(update, f"❌ {e}")
        return
    except Exception as e:
        log.error(f"cmd_addadmin: {e}")
        await _reply(update, t(lang, "err_generic"))
        return

    await _reply(update, f"✅ user_id={new_id} adicionado como admin.")


# ── Admin: /rmadmin <user_id> ─────────────────────────────────────────────────

async def cmd_rmadmin(update: Update, ctx):
    lang    = get_lang(update)
    caller  = update.effective_user.id
    if not await _is_admin(update):
        await _reply(update, t(lang, "err_access_denied"))
        return

    parts = update.message.text.strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await _reply(update, "Uso: /rmadmin <telegram_user_id>")
        return

    target_id = int(parts[1])
    if target_id == caller:
        await _reply(update, "❌ Não podes remover-te a ti próprio.")
        return

    try:
        await remove_admin(target_id)
    except ValueError as e:
        await _reply(update, f"❌ {e}")
        return
    except Exception as e:
        log.error(f"cmd_rmadmin: {e}")
        await _reply(update, t(lang, "err_generic"))
        return

    await _reply(update, f"✅ user_id={target_id} removido dos admins.")


# ── Admin: /admins ────────────────────────────────────────────────────────────

async def cmd_admins(update: Update, ctx):
    lang = get_lang(update)
    if not await _is_admin(update):
        await _reply(update, t(lang, "err_access_denied"))
        return

    try:
        admins = await list_admins()
    except Exception as e:
        log.error(f"cmd_admins: {e}")
        await _reply(update, t(lang, "err_generic"))
        return

    if not admins:
        await _reply(update, "Nenhum admin registado.")
        return

    lines = [
        f"• {a['user_id']}  (desde {a['added_at'][:10]}"
        + (f", por {a['added_by']}" if a['added_by'] else ", bootstrap") + ")"
        for a in admins
    ]
    await _reply(update, "👑 Administradores:\n\n" + "\n".join(lines))


# ── Handlers ──────────────────────────────────────────────────────────────────

ptb_app.add_handler(CommandHandler("start",      cmd_start))
ptb_app.add_handler(CommandHandler("produtos",   cmd_produtos))
ptb_app.add_handler(CommandHandler("ajuda",      cmd_ajuda))
ptb_app.add_handler(CommandHandler("botmaker",   cmd_botmaker))
ptb_app.add_handler(CommandHandler("pedidos",    cmd_pedidos))
ptb_app.add_handler(CommandHandler("addproduto", cmd_addproduto))
ptb_app.add_handler(CommandHandler("rmproduto",  cmd_rmproduto))
ptb_app.add_handler(CommandHandler("addadmin",   cmd_addadmin))
ptb_app.add_handler(CommandHandler("rmadmin",    cmd_rmadmin))
ptb_app.add_handler(CommandHandler("admins",     cmd_admins))

ptb_app.add_handler(MessageHandler(filters.Regex(r"^/comprar_\S+"), cmd_comprar))

ptb_app.add_handler(MessageHandler(filters.Regex(f"^({BTN_PRODUCTS_RE})$"), cmd_produtos))
ptb_app.add_handler(MessageHandler(filters.Regex(f"^({BTN_HELP_RE})$"),     cmd_ajuda))
ptb_app.add_handler(MessageHandler(filters.Regex(f"^({BTN_BOTMAKER_RE})$"), cmd_botmaker))
ptb_app.add_handler(MessageHandler(filters.Regex(f"^({BTN_ORDERS_RE})$"),   cmd_pedidos))
ptb_app.add_handler(MessageHandler(filters.Regex(f"^({BTN_ADD_RE})$"),      cmd_addproduto))
ptb_app.add_handler(MessageHandler(filters.Regex(f"^({BTN_REMOVE_RE})$"),   cmd_rmproduto))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
