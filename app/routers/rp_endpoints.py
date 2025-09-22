from fastapi import APIRouter, HTTPException, Request
from typing import Optional, Dict, Any
from ..settings import settings
from ..db import init_db
from ..providers.registry import get_provider_by_name, resolve_provider_by_payment_method

router = APIRouter()


@router.on_event("startup")
async def _startup():
    await init_db()


def _normalize_provider_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    n = name.strip().lower()
    if n in {"brusnika", "brusnika_sbp", "brusnika-sbp", "sbp-brusnika"}:
        return "Brusnika_SBP"
    return name


def _select_provider(provider_name: Optional[str], payment_method: Optional[str]):
    prov = get_provider_by_name(_normalize_provider_name(provider_name)) if provider_name else None
    if not prov and payment_method:
        prov = resolve_provider_by_payment_method(payment_method)
    if not prov:
        prov = get_provider_by_name(settings.DEFAULT_PROVIDER)
    if not prov:
        raise HTTPException(status_code=400, detail="Provider not found")
    return prov


def _normalize_nested_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Принимаем RP-вложенный формат и приводим к единому виду для адаптера.
    Ожидаем: settings / params.customer / payment / callback_url / processing_url
    """
    settings_in = (body.get("params", {}).get("settings") or body.get("settings") or {}) or {}
    customer_in = (body.get("params", {}).get("customer") or body.get("customer") or {}) or {}
    payment_in = (body.get("params", {}).get("payment") or body.get("payment") or {}) or {}

    callback_url = body.get("callback_url")
    processing_url = body.get("processing_url")
    method_name = body.get("method_name")

    # Обязательные поля
    if not payment_in or "order_number" not in payment_in:
        raise HTTPException(status_code=400, detail="payment.order_number is required")
    if "amount" not in payment_in:
        raise HTTPException(status_code=400, detail="payment.amount is required")
    if "currency" not in payment_in:
        raise HTTPException(status_code=400, detail="payment.currency is required")
    if not callback_url:
        raise HTTPException(status_code=400, detail="callback_url is required")
    if "token" not in payment_in:
        raise HTTPException(status_code=400, detail="payment.token is required")

    return {
        # ключи RP
        "rp_token": payment_in["token"],
        "order_number": payment_in["order_number"],
        "amount": int(payment_in["amount"]),
        "currency": str(payment_in["currency"]),
        "callback_url": callback_url,
        "redirect_success_url": payment_in.get("redirect_success_url"),
        "redirect_fail_url": payment_in.get("redirect_fail_url"),
        # провайдерские настройки
        "_provider_auth": settings_in.get("authorization_token"),
        "_provider_method": (settings_in.get("payment_method") or settings_in.get("method") or "SBP"),
        # доп. инфо
        "customer": customer_in or {},
        "processing_url": processing_url,
        "method_name": method_name,
        # флаги для QR обработки
        "wrapped_to_json": settings_in.get("wrapped_to_json") or body.get("wrapped_to_json"),
        "show_qr_on_form": settings_in.get("show_qr_on_form") or body.get("show_qr_on_form"),
        "_raw": body,  # для логов
    }


@router.post("/pay")
async def pay(body: Dict[str, Any]):
    """
    Вход — строго «вложенный» JSON, как ты прислал.
    Выход — внешний формат, понятный RP UI:
    {
      "status": "OK",
      "gateway_token": "...",
      "result": "pending|approved|declined",
      "requisites": {...},
      "redirectRequest": {"url": null|..., "type": "post_iframes"|"redirect", "iframes": []},
      "with_external_format": true,
      "provider_response_data": {...},
      "logs": [...]
    }
    """
    provider = _select_provider(
        (body.get("settings") or {}).get("provider"),
        (body.get("payment") or {}).get("paymentMethod"),
    )
    payload = _normalize_nested_payload(body)

    # Выполняем платёж у провайдера
    result = await provider.pay(payload)

    # Адаптер уже возвращает внешний формат — просто прокидываем
    return result


@router.post("/status")
async def status(body: Dict[str, Any]):
    """
    Поддерживаем nested-форму статуса от RP:
    { "payment": { "gateway_token": "...", "token": "...", "order_number": "..." } }
    Приоритет: gateway_token -> token (rp_token) -> order_number
    """
    payment = (body.get("params", {}).get("payment") or body.get("payment") or {}) or {}
    gw = payment.get("gateway_token")
    rp_token = payment.get("token")
    order_number = payment.get("order_number")

    if not (gw or rp_token or order_number):
        return {
            "result": "ERROR",
            "status": "declined",
            "details": "gateway_token or payment.token or payment.order_number is required",
            "amount": None,
            "currency": None,
            "logs": [],
        }

    # Достаём провайдера по маппингу в адаптере
    from ..db import get_mapping_by_token_any
    mapping_key = gw or rp_token or order_number
    mapping = await get_mapping_by_token_any(mapping_key)
    if not mapping:
        raise HTTPException(status_code=404, detail="Unknown token")

    provider = get_provider_by_name(mapping["provider"])
    if not provider:
        raise HTTPException(status_code=400, detail="Provider missing for token")

    result = await provider.status({
        "rp_token": rp_token,
        "order_number": order_number,
        "gateway_token": gw
    })
    return result


@router.post("/refund")
async def refund(body: Dict[str, Any]):
    from ..db import get_mapping_by_token_any
    payment = (body.get("params", {}).get("payment") or body.get("payment") or {}) or {}
    gw = payment.get("gateway_token")
    rp_token = payment.get("token")
    order_number = payment.get("order_number")

    key = gw or rp_token or order_number
    if not key:
        raise HTTPException(status_code=400, detail="gateway_token or payment.token or payment.order_number required")

    mapping = await get_mapping_by_token_any(key)
    if not mapping:
        raise HTTPException(status_code=404, detail="Unknown token")

    provider = get_provider_by_name(mapping["provider"])
    if not provider:
        raise HTTPException(status_code=400, detail="Provider missing for token")

    return await provider.refund(body)


@router.post("/payout")
async def payout(body: Dict[str, Any]):
    provider = _select_provider((body.get("settings") or {}).get("provider"), None)
    return await provider.payout(body)


@router.get("/qr_form/{gateway_token}")
async def qr_form(gateway_token: str):
    """
    Простая QR форма для отображения QR кода на нашей странице
    Используется когда show_qr_on_form = true
    """
    from ..db import get_mapping_by_token_any

    mapping = await get_mapping_by_token_any(gateway_token)
    if not mapping:
        raise HTTPException(status_code=404, detail="QR form not found")

    # Простая HTML форма с QR кодом
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>SBP Payment - QR Code</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: Arial, sans-serif; text-align: center; padding: 20px; }}
            .qr-container {{ max-width: 400px; margin: 0 auto; }}
            .qr-code {{ width: 300px; height: 300px; margin: 20px auto; }}
            .info {{ margin: 20px 0; }}
        </style>
    </head>
    <body>
        <div class="qr-container">
            <h2>SBP Payment</h2>
            <div class="info">
                <p><strong>Order:</strong> {mapping.get('order_number', 'N/A')}</p>
                <p><strong>Status:</strong> {mapping.get('status', 'pending')}</p>
            </div>
            <div class="qr-code">
                <p>Scan QR code to pay:</p>
                <div id="qr-placeholder">
                    <p>Loading QR code...</p>
                </div>
            </div>
        </div>
        <script>
            // Здесь можно добавить логику для отображения QR кода
            // или периодической проверки статуса платежа
            setTimeout(function() {{
                document.getElementById('qr-placeholder').innerHTML = '<p>QR code would be displayed here</p>';
            }}, 1000);
        </script>
    </body>
    </html>
    """

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_content, status_code=200)
