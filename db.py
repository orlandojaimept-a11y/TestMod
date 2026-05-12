"""
db.py — Camada de acesso ao Supabase
Todas as queries em um único lugar, fácil de testar ou trocar.

FIX: Supabase Python SDK é síncrono. Todas as funções foram convertidas para
     async usando asyncio.to_thread() para não bloquear o event loop do FastAPI/PTB.
"""

import os
import asyncio
import logging
from supabase import create_client, Client

log = logging.getLogger(__name__)

_client: Client = None

def _db() -> Client:
    global _client
    if _client is None:
        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_KEY"],
        )
    return _client


# ── Produtos ──────────────────────────────────────────────────────────────────

async def get_products() -> list[dict]:
    return await asyncio.to_thread(
        lambda: _db().table("products").select("*").eq("active", True).execute().data
    )


async def get_product(pid: str) -> dict | None:
    rows = await asyncio.to_thread(
        lambda: _db().table("products").select("*").eq("id", pid).execute().data
    )
    return rows[0] if rows else None


async def add_product(name: str, desc: str, price: float, currency: str, link: str):
    await asyncio.to_thread(
        lambda: _db().table("products").insert({
            "name": name,
            "description": desc,
            "price_usd": price,
            "currency": currency,
            "download_link": link,
            "active": True,
        }).execute()
    )
    log.info(f"Produto adicionado: {name}")


async def remove_product(pid: str):
    await asyncio.to_thread(
        lambda: _db().table("products").update({"active": False}).eq("id", pid).execute()
    )
    log.info(f"Produto desativado: {pid}")


# ── Pedidos ───────────────────────────────────────────────────────────────────

async def save_order(user_id: int, product_id: str, payment_id: str, amount, currency: str):
    await asyncio.to_thread(
        lambda: _db().table("orders").insert({
            "user_id": str(user_id),
            "product_id": product_id,
            "payment_id": str(payment_id),
            "amount": str(amount),
            "currency": currency,
            "status": "pending",
        }).execute()
    )
    log.info(f"Pedido salvo: payment_id={payment_id}")


async def get_order_by_payment(payment_id: str) -> dict | None:
    rows = await asyncio.to_thread(
        lambda: _db().table("orders")
            .select("*")
            .eq("payment_id", str(payment_id))
            .execute()
            .data
    )
    return rows[0] if rows else None


async def mark_paid(payment_id: str):
    await asyncio.to_thread(
        lambda: _db().table("orders").update({"status": "paid"}).eq("payment_id", str(payment_id)).execute()
    )
    log.info(f"Pedido marcado como pago: payment_id={payment_id}")


async def list_orders(limit: int = 15) -> list[dict]:
    return await asyncio.to_thread(
        lambda: _db().table("orders")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
    )
