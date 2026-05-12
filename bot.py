"""
LOJA DIGITAL — Bot Telegram
────────────────────────────
Pagamento : NowPayments (crypto) via IPN
Entrega   : link de download enviado pelo bot
Banco     : Supabase
Servidor  : FastAPI (webhook Telegram + IPN NowPayments)
Deploy    : Railway / Render / Fly.io

Compatível com python-telegram-bot >= 21.x
"""

import os
import json
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

from db import (
    get_products,
    get_product,
    add_product,
    remove_product,
    save_order,
    get_order_by_payment,
    mark_paid,
    list_orders,
)
from payments import create_payment, verify_ipn_signature

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

# ── Variáveis de ambiente obrigatórias ───────────────────────────────────────
BOT_TOKEN   = os.environ["BOT_TOKEN"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]   # ex: https://meuapp.railway.app
ADMIN_ID    = int(os.environ["ADMIN_TELEGRAM_ID"])

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"

# ── Estados do ConversationHandler (admin add product) ───────────────────────
AWAIT_NAME, AWAIT_DESC, AWAIT_PRICE, AWAIT_CURRENCY, AWAIT_LINK = range(5)
CURRENCIES = ["USDTTRC20", "BTC", "ETH", "BNB", "LTC"]

# Limite de pedidos exibidos no painel admin (evita mensagem > 4096 chars)
ORDERS_DISPLAY_LIMIT = 20

# ── Setup da Application do python-telegram-bot ──────────────────────────────
# FIX PTB 21.x: ApplicationBuilder continua igual, mas o lifespan é gerenciado
# externamente (updater=None). Nenhuma mudança de API aqui.
ptb_app = Application.builder().token(BOT_TOKEN).updater(None).build()

# ── Lifecycle FastAPI ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await ptb_app.initialize()
    await ptb_app.start()

    webhook_full = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await ptb_app.bot.set_webhook(
        url=webhook_full,
        allowed_updates=Update.ALL_TYPES,
    )
    log.info(f"Webhook registrado: {webhook_full}")

    yield

    await ptb_app.bot.delete_webhook()
    await ptb_app.stop()
    await ptb_app.shutdown()

api = FastAPI(lifespan=lifespan)

# ── Rota: recebe updates do Telegram ─────────────────────────────────────────
@api.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    body = await request.json()
    update = Update.de_json(body, ptb_app.bot)
    await ptb_app.process_update(update)
    return Response(status_code=200)

# ── Rota: IPN do NowPayments ──────────────────────────────────────────────────
@api.post("/ipn")
async def nowpayments_ipn(request: Request):
    sig  = request.headers.get("x-nowpayments-sig", "")
    body = await request.body()

    if not verify_ipn_signature(body, sig):
        log.warning("IPN com assinatura inválida.")
        return Response(status_code=401)

    data           = json.loads(body)
    payment_id     = str(data.get("payment_id", ""))
    payment_status = data.get("payment_status", "")

    log.info(f"IPN recebido | payment_id={payment_id} status={payment_status}")

    if payment_status in ("finished", "confirmed"):
        order = get_order_by_payment(payment_id)
        if not order:
            log.warning(f"Pedido não encontrado para payment_id={payment_id}")
            return Response(status_code=200)

        if order["status"] == "paid":
            log.info("Pedido já marcado como pago, ignorando.")
            return Response(status_code=200)

        mark_paid(payment_id)

        product = get_product(order["product_id"])
        if product:
            await _send_download(int(order["user_id"]), product)
            log.info(f"Download enviado para user_id={order['user_id']}")

    return Response(status_code=200)

# ── Rota: healthcheck ─────────────────────────────────────────────────────────
@api.get("/")
async def root():
    return {"status": "ok"}

@api.get("/health")
async def health():
    return {"status": "ok"}

# ── Helper: escapa caracteres especiais para MarkdownV2 ──────────────────────
def _esc(text: str) -> str:
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in str(text))

# ── Helper: envia link de download ───────────────────────────────────────────
async def _send_download(user_id: int, product: dict):
    text = (
        f"✅ *Pagamento confirmado\\!*\n\n"
        f"Produto: *{_esc(product['name'])}*\n\n"
        f"🔗 Seu link de download:\n`{_esc(product['download_link'])}`\n\n"
        f"Obrigado pela compra\\! 🙏"
    )
    await ptb_app.bot.send_message(
        chat_id=user_id,
        text=text,
        parse_mode="MarkdownV2",
    )

# ── /start ────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx):
    keyboard = [[InlineKeyboardButton("🛒 Ver Produtos", callback_data="catalog:0")]]
    await update.message.reply_text(
        "👋 Bem\\-vindo à *Loja Digital*\\!\n\n"
        "Produtos digitais entregues instantaneamente após o pagamento\\.",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# ── Catálogo ──────────────────────────────────────────────────────────────────
async def cb_catalog(update: Update, ctx):
    query = update.callback_query
    await query.answer()

    page     = int(query.data.split(":")[1])
    products = get_products()

    if not products:
        await query.edit_message_text("😔 Nenhum produto disponível no momento.")
        return

    PAGE      = 3
    total_pgs = max(1, -(-len(products) // PAGE))  # ceil division
    chunk     = products[page * PAGE : (page + 1) * PAGE]

    buttons = [
        [InlineKeyboardButton(
            f"{p['name']}  —  ${p['price_usd']:.2f}",
            callback_data=f"product:{p['id']}",
        )]
        for p in chunk
    ]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Anterior", callback_data=f"catalog:{page - 1}"))
    if page < total_pgs - 1:
        nav.append(InlineKeyboardButton("Próximo ▶", callback_data=f"catalog:{page + 1}"))
    if nav:
        buttons.append(nav)

    await query.edit_message_text(
        f"📦 *Produtos disponíveis* \\({page + 1}/{total_pgs}\\):",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

# ── Detalhe do produto ────────────────────────────────────────────────────────
async def cb_product(update: Update, ctx):
    query = update.callback_query
    await query.answer()

    pid = query.data.split(":")[1]
    p   = get_product(pid)

    if not p:
        await query.edit_message_text("Produto não encontrado.")
        return

    buttons = [
        [InlineKeyboardButton("💳 Comprar agora", callback_data=f"buy:{pid}")],
        [InlineKeyboardButton("◀ Voltar",         callback_data="catalog:0")],
    ]
    await query.edit_message_text(
        f"*{_esc(p['name'])}*\n\n"
        f"{_esc(p['description'])}\n\n"
        f"💵 Preço: *\\${p['price_usd']:.2f}*\n"
        f"💱 Pago em: `{p['currency']}`",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

# ── Comprar ───────────────────────────────────────────────────────────────────
async def cb_buy(update: Update, ctx):
    query = update.callback_query
    await query.answer("⏳ Gerando pagamento…")

    pid = query.data.split(":")[1]
    p   = get_product(pid)
    uid = query.from_user.id

    if not p:
        await query.edit_message_text("Produto não encontrado.")
        return

    try:
        payment = await create_payment(p, uid)
    except Exception as e:
        log.error(f"Erro NowPayments: {e}")
        await query.edit_message_text(
            "❌ Erro ao gerar pagamento\\. Tente novamente mais tarde\\.",
            parse_mode="MarkdownV2",
        )
        return

    save_order(uid, pid, payment["payment_id"], payment["pay_amount"], payment["pay_currency"])

    address = payment.get("pay_address", "—")
    amount  = payment.get("pay_amount", "—")
    curr    = payment.get("pay_currency", "—").upper()

    buttons = [[InlineKeyboardButton("◀ Voltar ao catálogo", callback_data="catalog:0")]]
    await query.edit_message_text(
        f"🧾 *Pedido criado\\!*\n\n"
        f"Produto: *{_esc(p['name'])}*\n\n"
        f"Envie exatamente:\n"
        f"`{_esc(str(amount))} {_esc(curr)}`\n\n"
        f"Para o endereço:\n"
        f"`{_esc(str(address))}`\n\n"
        f"⏳ O link de download será enviado aqui assim que o pagamento for confirmado\\.",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

# ── Admin: menu ───────────────────────────────────────────────────────────────
def _is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID

def _admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Adicionar produto", callback_data="adm:add")],
        [InlineKeyboardButton("🗑 Remover produto",   callback_data="adm:remove")],
        [InlineKeyboardButton("📋 Ver pedidos",        callback_data="adm:orders")],
        [InlineKeyboardButton("❌ Fechar",             callback_data="adm:close")],
    ])

async def cmd_admin(update: Update, ctx):
    if not _is_admin(update):
        await update.message.reply_text("⛔ Acesso negado.")
        return

    await update.message.reply_text(
        "🔧 *Painel Admin*",
        parse_mode="MarkdownV2",
        reply_markup=_admin_keyboard(),
    )

# FIX: cb_admin NÃO trata "add" — exclusivo do ConversationHandler
async def cb_admin(update: Update, ctx):
    query  = update.callback_query
    await query.answer()
    action = query.data.split(":")[1]

    if action == "close":
        await query.edit_message_text("Painel fechado\\.", parse_mode="MarkdownV2")

    elif action == "orders":
        orders = list_orders(limit=ORDERS_DISPLAY_LIMIT)
        if not orders:
            await query.edit_message_text("Nenhum pedido ainda\\.", parse_mode="MarkdownV2")
            return
        lines = [
            f"• `{_esc(o['payment_id'][:12])}…` \\| {_esc(o['status'])} \\| "
            f"`{_esc(str(o['amount']))} {_esc(o['currency'])}` \\| uid:`{o['user_id']}`"
            for o in orders
        ]
        body = "\n".join(lines)
        if len(body) > 3800:
            body = body[:3800] + "\n\\.\\.\\."
        await query.edit_message_text(
            f"📋 *Últimos {len(orders)} pedidos:*\n\n" + body,
            parse_mode="MarkdownV2",
        )

    elif action == "remove":
        prods = get_products()
        if not prods:
            await query.edit_message_text("Nenhum produto para remover\\.", parse_mode="MarkdownV2")
            return
        buttons = [
            [InlineKeyboardButton(f"🗑 {p['name']}", callback_data=f"adm_del:{p['id']}")]
            for p in prods
        ]
        buttons.append([InlineKeyboardButton("◀ Voltar", callback_data="adm:back")])
        await query.edit_message_text(
            "Qual produto deseja desativar?",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif action == "back":
        await query.edit_message_text(
            "🔧 *Painel Admin*",
            parse_mode="MarkdownV2",
            reply_markup=_admin_keyboard(),
        )

async def cb_admin_del(update: Update, ctx):
    query = update.callback_query
    await query.answer()
    pid = query.data.split(":")[1]
    remove_product(pid)
    await query.edit_message_text("✅ Produto desativado\\.", parse_mode="MarkdownV2")

# ── Admin: adicionar produto (ConversationHandler) ────────────────────────────
async def adm_add_start(update: Update, ctx):
    """Entrada via callback 'adm:add'."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📝 Nome do produto:")
    return AWAIT_NAME

async def adm_recv_name(update: Update, ctx):
    ctx.user_data["np"] = {"name": update.message.text.strip()}
    await update.message.reply_text("📝 Descrição:")
    return AWAIT_DESC

async def adm_recv_desc(update: Update, ctx):
    ctx.user_data["np"]["description"] = update.message.text.strip()
    await update.message.reply_text("💵 Preço em USD \\(ex: 9\\.99\\):", parse_mode="MarkdownV2")
    return AWAIT_PRICE

async def adm_recv_price(update: Update, ctx):
    try:
        price = float(update.message.text.strip().replace(",", "."))
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Preço inválido\\. Digite um número positivo \\(ex: 9\\.99\\):",
            parse_mode="MarkdownV2",
        )
        return AWAIT_PRICE

    ctx.user_data["np"]["price"] = price
    buttons = [[InlineKeyboardButton(c, callback_data=f"curr:{c}")] for c in CURRENCIES]
    await update.message.reply_text(
        "💱 Moeda de pagamento:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return AWAIT_CURRENCY

async def adm_recv_currency(update: Update, ctx):
    query = update.callback_query
    await query.answer()
    ctx.user_data["np"]["currency"] = query.data.split(":")[1]
    await query.edit_message_text("🔗 Link de download \\(URL completa\\):", parse_mode="MarkdownV2")
    return AWAIT_LINK

async def adm_recv_link(update: Update, ctx):
    link = update.message.text.strip()
    if not (link.startswith("http://") or link.startswith("https://")):
        await update.message.reply_text(
            "❌ Link inválido\\. Envie uma URL completa começando com `https://`:",
            parse_mode="MarkdownV2",
        )
        return AWAIT_LINK

    np = ctx.user_data["np"]
    np["link"] = link
    add_product(np["name"], np["description"], np["price"], np["currency"], np["link"])
    await update.message.reply_text(
        f"✅ Produto *{_esc(np['name'])}* adicionado\\!",
        parse_mode="MarkdownV2",
    )
    ctx.user_data.pop("np", None)
    return ConversationHandler.END

async def adm_cancel(update: Update, ctx):
    ctx.user_data.pop("np", None)
    await update.message.reply_text("❌ Operação cancelada\\.", parse_mode="MarkdownV2")
    return ConversationHandler.END

# ── Registro dos handlers ─────────────────────────────────────────────────────
# FIX: ConversationHandler registrado PRIMEIRO (group=-1) para ter prioridade
# sobre os handlers avulsos. Isso evita que "adm:add" seja capturado pelo
# cb_admin antes de entrar na conversa.
admin_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(adm_add_start, pattern=r"^adm:add$")],
    states={
        AWAIT_NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_recv_name)],
        AWAIT_DESC:     [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_recv_desc)],
        AWAIT_PRICE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_recv_price)],
        AWAIT_CURRENCY: [CallbackQueryHandler(adm_recv_currency, pattern=r"^curr:.+$")],
        AWAIT_LINK:     [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_recv_link)],
    },
    fallbacks=[CommandHandler("cancel", adm_cancel)],
    per_message=False,
    per_chat=True,
    per_user=True,
)
# group=-1 garante que o ConversationHandler é processado antes dos demais
ptb_app.add_handler(admin_conv, group=-1)

ptb_app.add_handler(CommandHandler("start", cmd_start))
ptb_app.add_handler(CommandHandler("admin", cmd_admin))

ptb_app.add_handler(CallbackQueryHandler(cb_catalog,   pattern=r"^catalog:\d+$"))
ptb_app.add_handler(CallbackQueryHandler(cb_product,   pattern=r"^product:.+$"))
ptb_app.add_handler(CallbackQueryHandler(cb_buy,       pattern=r"^buy:.+$"))

# FIX: "add" removido do padrão — tratado exclusivamente pelo ConversationHandler
ptb_app.add_handler(CallbackQueryHandler(cb_admin,     pattern=r"^adm:(remove|orders|close|back)$"))
ptb_app.add_handler(CallbackQueryHandler(cb_admin_del, pattern=r"^adm_del:.+$"))

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))  # Define 10000 como padrão se PORT não estiver setado
    uvicorn.run(api, host="0.0.0.0", port=port)
