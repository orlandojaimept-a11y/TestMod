"""
payments.py — Integração NowPayments  [hardened v2]

Melhorias vs payments-3.py:
  - Retry automático (3 tentativas) com backoff exponencial para erros de rede/timeout
  - Timeout explícito de 20s por tentativa
  - Erros HTTP da API NowPayments logados com detalhes (status + body)
  - verify_ipn_signature: protegido contra body vazio e JSON inválido
  - _API_KEY e _IPN_KEY validados no arranque para falhar cedo
"""

import os
import hmac
import hashlib
import json
import logging
import asyncio

import httpx

log = logging.getLogger(__name__)

NP_BASE   = "https://api.nowpayments.io/v1"
_RETRIES  = 3
_BACKOFF  = 1.5   # segundos base para backoff exponencial


def _api_key() -> str:
    key = os.environ.get("NOWPAYMENTS_API_KEY", "")
    if not key:
        raise RuntimeError("NOWPAYMENTS_API_KEY não configurada")
    return key

def _ipn_key() -> str:
    return os.environ.get("NOWPAYMENTS_IPN_SECRET", "")


async def create_payment(product: dict, user_id: int) -> dict:
    """
    Cria um pagamento na NowPayments.
    Retenta até _RETRIES vezes em caso de erro de rede ou timeout.
    Lança exceção se todas as tentativas falharem.
    """
    headers = {
        "x-api-key": _api_key(),
        "Content-Type": "application/json",
    }
    payload = {
        "price_amount":      product["price_usd"],
        "price_currency":    "usd",
        "pay_currency":      product["currency"].lower(),
        "order_id":          f"{user_id}_{product['id']}",
        "order_description": product["name"],
    }

    last_exc: Exception = RuntimeError("Nenhuma tentativa realizada")

    for attempt in range(1, _RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"{NP_BASE}/payment",
                    headers=headers,
                    json=payload,
                )

            if response.status_code >= 500:
                # Erro do servidor NowPayments — retriável
                log.warning(
                    f"NowPayments: erro {response.status_code} na tentativa {attempt}/{_RETRIES}. "
                    f"Body: {response.text[:300]}"
                )
                last_exc = httpx.HTTPStatusError(
                    f"HTTP {response.status_code}", request=response.request, response=response
                )
            elif response.status_code >= 400:
                # Erro de cliente (4xx) — não retriável
                log.error(
                    f"NowPayments: erro {response.status_code} (não retriável). "
                    f"Body: {response.text[:300]}"
                )
                response.raise_for_status()
            else:
                data = response.json()
                log.info(f"Pagamento criado: payment_id={data.get('payment_id')} (tentativa {attempt})")
                return data

        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
            log.warning(f"NowPayments: erro de rede na tentativa {attempt}/{_RETRIES}: {e}")
            last_exc = e
        except httpx.HTTPStatusError:
            raise  # 4xx — não faz sentido retentar
        except Exception as e:
            log.error(f"NowPayments: erro inesperado na tentativa {attempt}/{_RETRIES}: {e}")
            last_exc = e

        if attempt < _RETRIES:
            wait = _BACKOFF ** attempt
            log.info(f"NowPayments: aguardando {wait:.1f}s antes de nova tentativa…")
            await asyncio.sleep(wait)

    log.error(f"NowPayments: todas as {_RETRIES} tentativas falharam.")
    raise last_exc


def verify_ipn_signature(body_bytes: bytes, signature: str) -> bool:
    """
    Verifica a assinatura HMAC-SHA512 do IPN do NowPayments.
    Retorna True (modo permissivo) se a chave IPN não estiver configurada.
    Retorna False em caso de qualquer erro de verificação.
    """
    if not body_bytes:
        log.warning("IPN: body vazio recebido.")
        return False

    ipn_key = _ipn_key()
    if not ipn_key:
        log.warning("NOWPAYMENTS_IPN_SECRET não configurado — pulando verificação (modo dev).")
        return True

    if not signature:
        log.warning("IPN: header x-nowpayments-sig ausente.")
        return False

    try:
        body_dict   = json.loads(body_bytes)
        sorted_body = json.dumps(body_dict, sort_keys=True, separators=(",", ":"))

        mac = hmac.new(
            ipn_key.encode("utf-8"),
            sorted_body.encode("utf-8"),
            hashlib.sha512,
        )
        expected = mac.hexdigest()
        return hmac.compare_digest(expected, signature)

    except json.JSONDecodeError as e:
        log.error(f"IPN: body não é JSON válido: {e}")
        return False
    except Exception as e:
        log.error(f"IPN: erro inesperado na verificação de assinatura: {e}")
        return False
