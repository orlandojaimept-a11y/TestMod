-- ── schema.sql — Execute no SQL Editor do Supabase ─────────────────────────

-- Tabela de produtos
CREATE TABLE IF NOT EXISTS products (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT    NOT NULL,
    description  TEXT    NOT NULL DEFAULT '',
    price_usd    NUMERIC(10, 2) NOT NULL,
    currency     TEXT    NOT NULL,          -- ex: USDTTRC20, BTC
    download_link TEXT   NOT NULL,
    active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tabela de pedidos
CREATE TABLE IF NOT EXISTS orders (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      TEXT    NOT NULL,          -- Telegram user_id
    product_id   UUID    REFERENCES products(id),
    payment_id   TEXT    NOT NULL UNIQUE,   -- ID do NowPayments
    amount       TEXT    NOT NULL,          -- valor em cripto
    currency     TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'pending', -- pending | paid
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índices úteis
CREATE INDEX IF NOT EXISTS idx_orders_payment_id ON orders(payment_id);
CREATE INDEX IF NOT EXISTS idx_orders_user_id    ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_products_active   ON products(active);

-- RLS: desative para uso interno com service_role key
-- (sua SUPABASE_KEY deve ser a service_role, não a anon key)
ALTER TABLE products DISABLE ROW LEVEL SECURITY;
ALTER TABLE orders   DISABLE ROW LEVEL SECURITY;
