# Loja Digital — Bot Telegram

Bot de vendas de produtos digitais com pagamento em crypto via NowPayments e entrega automática por link.

## Estrutura

```
lojabot/
├── bot.py           # Lógica principal (handlers + FastAPI)
├── db.py            # Acesso ao Supabase
├── payments.py      # Integração NowPayments
├── schema.sql       # Tabelas do banco (rode no Supabase)
├── requirements.txt
└── .env.example
```

## Pré-requisitos

- Python 3.11+
- Bot criado no [@BotFather](https://t.me/BotFather)
- Projeto no [Supabase](https://supabase.com)
- Conta no [NowPayments](https://nowpayments.io)

---

## 1. Banco de dados (Supabase)

1. Abra o **SQL Editor** no painel do Supabase
2. Cole e execute o conteúdo de `schema.sql`
3. Copie a **service_role key** em *Settings → API* (não use a anon key)

---

## 2. Variáveis de ambiente

```bash
cp .env.example .env
# Edite .env com seus valores reais
```

---

## 3. NowPayments — configurar IPN

1. Acesse *Account Settings → IPN Settings* no NowPayments
2. Informe a URL: `https://SEU_APP/ipn`
3. Copie a **IPN Secret Key** e cole em `NOWPAYMENTS_IPN_SECRET`

> ⚠️ O NowPayments exige HTTPS. Em dev local, use [ngrok](https://ngrok.com):
> ```bash
> ngrok http 8000
> # Use a URL https gerada como WEBHOOK_URL e para o IPN
> ```

---

## 4. Rodar localmente

```bash
pip install -r requirements.txt
uvicorn bot:api --reload --port 8000
```

---

## 5. Deploy no Railway

1. Crie um novo projeto e conecte o repositório
2. Adicione as variáveis de ambiente do `.env` em *Variables*
3. O Railway detecta automaticamente o `requirements.txt`
4. Defina o **Start Command**:
   ```
   uvicorn bot:api --host 0.0.0.0 --port $PORT
   ```
5. Após o deploy, copie a URL pública e atualize `WEBHOOK_URL`

### Deploy no Render

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn bot:api --host 0.0.0.0 --port $PORT`
- Adicione as variáveis em *Environment*

---

## Comandos do bot

| Comando   | Quem pode usar | Descrição                    |
|-----------|----------------|------------------------------|
| `/start`  | Todos          | Abre o catálogo              |
| `/admin`  | Admin          | Painel: add/remover produtos, ver pedidos |
| `/cancel` | Admin          | Cancela o fluxo de adicionar produto |

---

## Fluxo de pagamento

```
Usuário clica "Comprar"
    → bot cria pagamento na NowPayments (async)
    → salva pedido com status "pending" no Supabase
    → exibe endereço + valor para o usuário

Usuário envia o crypto
    → NowPayments detecta o pagamento
    → envia IPN POST /ipn com status "confirmed" ou "finished"
    → bot verifica assinatura HMAC-SHA512
    → marca pedido como "paid"
    → envia link de download para o usuário via Telegram
```

---

## Problemas comuns

**Bot não responde após deploy**
→ Verifique se `WEBHOOK_URL` está correto e acessível publicamente.
→ Acesse `/health` no browser para confirmar que o servidor está rodando.

**IPN não chega**
→ Confirme a URL de IPN no painel do NowPayments.
→ O endpoint deve ser acessível sem autenticação (a verificação é via HMAC).

**Erro de permissão no Supabase**
→ Certifique-se de usar a `service_role key`, não a `anon key`.
→ O schema desativa RLS — adequado para uso server-side.
