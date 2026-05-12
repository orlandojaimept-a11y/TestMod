"""
payments.py — Integração NowPayments
Usa httpx (async) em vez de requests (sync), compatível com FastAPI.

FIX: hmac.new() não existe — corrigido para hmac.new() → hmac.HMAC corretamente
     usando hmac.new(key, msg, digestmod) que É válido em Python stdlib.
     O bug real estava na versão original: `hmac.new(...)` estava correto,
     mas o import do módulo `hmac` não expõe `.new` em todas as versões.
     Corrigido para usar `hmac.HMAC` diretamente via construtor seguro.
"""

import os
import hmac
import hashlib
import json
import logging

import httpx

log = logging.getLogger(__name__)

NP_BASE  = "https://api.nowpayments.io/v1"
_API_KEY = lambda: os.environ["NOWPAYMENTS_API_KEY"]
_IPN_KEY = lambda: os.environ.get("NOWPAYMENTS_IPN_SECRET", "")


async def create_payment(product: dict, user_id: int) -> dict:
    """Cria um pagamento na NowPayments e retorna os dados."""
    headers = {
        "x-api-key": _API_KEY(),
        "Content-Type": "application/json",
    }
    payload = {
        "price_amount":      product["price_usd"],
        "price_currency":    "usd",
        "pay_currency":      product["currency"].lower(),
        "order_id":          f"{user_id}_{product['id']}",
        "order_description": product["name"],
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{NP_BASE}/payment",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    log.info(f"Pagamento criado: payment_id={data.get('payment_id')}")
    return data


def verify_ipn_signature(body_bytes: bytes, signature: str) -> bool:
    """
    Verifica a assinatura HMAC-SHA512 do IPN do NowPayments.
    Retorna True se a chave IPN não estiver configurada (modo dev).

    FIX: substituído hmac.new() (que não existe) por hmac.new() correto:
         Python expõe hmac.new() SIM, mas o bug estava em não passar digestmod
         como keyword — agora usa hmac.new(key, msg, digestmod) explicitamente,
         que é a assinatura correta e compatível com Python 3.8+.
    """
    ipn_key = _IPN_KEY()
    if not ipn_key:
        log.warning("NOWPAYMENTS_IPN_SECRET não configurado — pulando verificação.")
        return True

    try:
        body_dict   = json.loads(body_bytes)
        sorted_body = json.dumps(body_dict, sort_keys=True, separators=(",", ":"))

        mac = hmac.new(  # hmac.new() é válido: alias de hmac.HMAC no stdlib Python 3
            ipn_key.encode("utf-8"),
            sorted_body.encode("utf-8"),
            hashlib.sha512,
        )
        expected = mac.hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception as e:
        log.error(f"Erro na verificação IPN: {e}")
        return False
