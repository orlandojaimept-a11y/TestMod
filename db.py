"""
db.py — Camada de acesso ao Supabase
Todas as queries em um único lugar, fácil de testar ou trocar.
"""

import os
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

def get_products() -> list[dict]:
    return _db().table("products").select("*").eq("active", True).execute().data


def get_product(pid: str) -> dict | None:
    rows = _db().table("products").select("*").eq("id", pid).execute().data
    return rows[0] if rows else None


def add_product(name: str, desc: str, price: float, currency: str, link: str):
    _db().table("products").insert({
        "name": name,
        "description": desc,
        "price_usd": price,
        "currency": currency,
        "download_link": link,
        "active": True,
    }).execute()
    log.info(f"Produto adicionado: {name}")


def remove_product(pid: str):
    _db().table("products").update({"active": False}).eq("id", pid).execute()
    log.info(f"Produto desativado: {pid}")


# ── Pedidos ───────────────────────────────────────────────────────────────────

def save_order(user_id: int, product_id: str, payment_id: str, amount, currency: str):
    _db().table("orders").insert({
        "user_id": str(user_id),
        "product_id": product_id,
        "payment_id": str(payment_id),
        "amount": str(amount),
        "currency": currency,
        "status": "pending",
    }).execute()
    log.info(f"Pedido salvo: payment_id={payment_id}")


def get_order_by_payment(payment_id: str) -> dict | None:
    rows = (
        _db().table("orders")
        .select("*")
        .eq("payment_id", str(payment_id))
        .execute()
        .data
    )
    return rows[0] if rows else None


def mark_paid(payment_id: str):
    _db().table("orders").update({"status": "paid"}).eq("payment_id", str(payment_id)).execute()
    log.info(f"Pedido marcado como pago: payment_id={payment_id}")


def list_orders(limit: int = 15) -> list[dict]:
    return (
        _db().table("orders")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )
