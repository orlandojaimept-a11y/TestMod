"""
db.py — Camada de dados da Loja Digital

Motor:   SQLite via aiosqlite (async, zero dependências externas de servidor)
Schema:  products + orders, criados automaticamente no primeiro arranque.

Convenções:
  - Todos os IDs de produto são UUID4 gerados aqui.
  - Produtos nunca são apagados fisicamente: ficam com active=0 (soft delete).
  - Pedidos têm status 'pending' → 'paid' (transição única, idempotente).
  - Inputs validados antes de qualquer escrita; ValueError em caso de dados inválidos.
  - Sem SQL dinâmico concatenado: todos os valores passam como parâmetros.
"""

import asyncio
import logging
import os
import re
import uuid
from typing import Optional

import aiosqlite

log = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "loja.db")

_URL_RE   = re.compile(r"^https?://\S+$")
_UUID_RE  = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_MAX_STR  = 512   # comprimento máximo de campos de texto livres


# ── Bootstrap ─────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Cria as tabelas se não existirem. Chamado no arranque da aplicação."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id            TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                description   TEXT NOT NULL DEFAULT '',
                price_usd     REAL NOT NULL CHECK(price_usd > 0),
                currency      TEXT NOT NULL DEFAULT 'BNB',
                download_link TEXT NOT NULL,
                active        INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                product_id    TEXT NOT NULL,
                payment_id    TEXT NOT NULL UNIQUE,
                amount        REAL NOT NULL,
                currency      TEXT NOT NULL,
                status        TEXT NOT NULL DEFAULT 'pending',
                created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                paid_at       TEXT,
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_orders_payment_id ON orders(payment_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)"
        )
        await db.commit()
    log.info(f"DB inicializada: {DB_PATH}")


# ── Validação interna ─────────────────────────────────────────────────────────

def _validate_product_id(pid: str) -> str:
    pid = str(pid).strip()
    if not _UUID_RE.match(pid):
        raise ValueError(f"product_id inválido: '{pid[:40]}'")
    return pid

def _validate_str(value: str, field: str, max_len: int = _MAX_STR) -> str:
    value = str(value).strip()
    if not value:
        raise ValueError(f"'{field}' não pode estar vazio")
    if len(value) > max_len:
        raise ValueError(f"'{field}' demasiado longo (máx {max_len} caracteres)")
    return value

def _validate_url(url: str) -> str:
    url = str(url).strip()
    if not _URL_RE.match(url):
        raise ValueError(f"URL inválido: '{url[:80]}'")
    return url

def _row_to_product(row: aiosqlite.Row) -> dict:
    return {
        "id":            row["id"],
        "name":          row["name"],
        "description":   row["description"],
        "price_usd":     row["price_usd"],
        "currency":      row["currency"],
        "download_link": row["download_link"],
        "active":        bool(row["active"]),
        "created_at":    row["created_at"],
    }

def _row_to_order(row: aiosqlite.Row) -> dict:
    return {
        "id":         row["id"],
        "user_id":    row["user_id"],
        "product_id": row["product_id"],
        "payment_id": row["payment_id"],
        "amount":     row["amount"],
        "currency":   row["currency"],
        "status":     row["status"],
        "created_at": row["created_at"],
        "paid_at":    row["paid_at"],
    }


# ── Produtos ─────────────────────────────────────────────────────────────────

async def get_products() -> list[dict]:
    """Devolve todos os produtos ativos, ordenados por nome."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM products WHERE active = 1 ORDER BY name COLLATE NOCASE"
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_product(r) for r in rows]


async def get_product(product_id: str) -> Optional[dict]:
    """
    Devolve um produto ativo pelo seu ID, ou None se não existir.
    Lança ValueError se o product_id tiver formato inválido.
    """
    pid = _validate_product_id(product_id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM products WHERE id = ? AND active = 1", (pid,)
        ) as cursor:
            row = await cursor.fetchone()
    return _row_to_product(row) if row else None


async def add_product(
    name: str,
    description: str,
    price_usd: float,
    currency: str,
    download_link: str,
) -> dict:
    """
    Insere um novo produto e devolve o registo criado.
    Lança ValueError se algum campo for inválido.
    """
    name          = _validate_str(name, "name", max_len=128)
    description   = _validate_str(description, "description")
    currency      = _validate_str(currency, "currency", max_len=16).upper()
    download_link = _validate_url(download_link)

    price_usd = float(price_usd)
    if price_usd <= 0:
        raise ValueError("price_usd deve ser positivo")

    pid = str(uuid.uuid4())

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO products (id, name, description, price_usd, currency, download_link)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (pid, name, description, price_usd, currency, download_link),
        )
        await db.commit()
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM products WHERE id = ?", (pid,)) as cur:
            row = await cur.fetchone()

    log.info(f"Produto criado: id={pid} name='{name}' price={price_usd}")
    return _row_to_product(row)


async def remove_product(product_id: str) -> None:
    """
    Desativa (soft delete) um produto pelo ID.
    Lança ValueError se o ID for inválido ou o produto não existir.
    """
    pid = _validate_product_id(product_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM products WHERE id = ? AND active = 1", (pid,)
        ) as cur:
            if not await cur.fetchone():
                raise ValueError(f"Produto '{pid}' não encontrado ou já inativo")
        await db.execute(
            "UPDATE products SET active = 0 WHERE id = ?", (pid,)
        )
        await db.commit()
    log.info(f"Produto desativado: id={pid}")


# ── Pedidos ───────────────────────────────────────────────────────────────────

async def save_order(
    user_id: int,
    product_id: str,
    payment_id: str,
    amount: float,
    currency: str,
) -> dict:
    """
    Guarda um novo pedido com status 'pending'.
    payment_id é UNIQUE — segunda inserção com o mesmo ID lança IntegrityError.
    """
    pid        = _validate_product_id(product_id)
    payment_id = _validate_str(payment_id, "payment_id", max_len=256)
    currency   = _validate_str(currency, "currency", max_len=16).upper()
    amount     = float(amount)
    user_id    = int(user_id)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO orders (user_id, product_id, payment_id, amount, currency)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, pid, payment_id, amount, currency),
        )
        await db.commit()
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM orders WHERE payment_id = ?", (payment_id,)
        ) as cur:
            row = await cur.fetchone()

    log.info(f"Pedido criado: payment_id={payment_id[:12]}… user_id={user_id}")
    return _row_to_order(row)


async def get_order_by_payment(payment_id: str) -> Optional[dict]:
    """
    Devolve um pedido pelo payment_id, ou None se não existir.
    Lança ValueError se o payment_id estiver vazio ou for demasiado longo.
    """
    payment_id = _validate_str(payment_id, "payment_id", max_len=256)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM orders WHERE payment_id = ?", (payment_id,)
        ) as cur:
            row = await cur.fetchone()
    return _row_to_order(row) if row else None


async def mark_paid(payment_id: str) -> None:
    """
    Marca um pedido como pago. Idempotente: não falha se já estiver pago.
    Lança ValueError se o pedido não existir.
    """
    payment_id = _validate_str(payment_id, "payment_id", max_len=256)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, status FROM orders WHERE payment_id = ?", (payment_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            raise ValueError(f"Pedido não encontrado: payment_id='{payment_id[:12]}…'")
        if row[1] == "paid":
            log.info(f"mark_paid: pedido {payment_id[:12]}… já estava pago. Ignorado.")
            return
        await db.execute(
            "UPDATE orders SET status = 'paid', paid_at = datetime('now') WHERE payment_id = ?",
            (payment_id,),
        )
        await db.commit()
    log.info(f"Pedido marcado como pago: payment_id={payment_id[:12]}…")


async def list_orders(limit: int = 20) -> list[dict]:
    """Devolve os pedidos mais recentes, ordenados do mais recente para o mais antigo."""
    limit = max(1, min(int(limit), 200))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
    return [_row_to_order(r) for r in rows]
