from fastapi import APIRouter, Request, Header, HTTPException
from ..db import get_mapping_by_token_any, update_status_by_token_any
from ..callbacks.rp_client import RPCallbackClient
from ..settings import settings
import hashlib

router = APIRouter()


def _to_rp_result(provider_status: str | None) -> str:
    s = (provider_status or "").lower()
    if s in {"paid", "success", "confirmed"}:
        return "approved"
    if s in {"cancelled", "canceled", "declined", "failed", "expired"}:
        return "declined"
    return "pending"


@router.post("/provider/brusnika/webhook")
async def brusnika_webhook(request: Request, x_signature: str | None = Header(default=None)):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    order_number = payload.get("merchantOrderId") or payload.get("orderId")
    provider_status = payload.get("status")
    platform_id = payload.get("idPlatform") or payload.get("platformOperationId")

    if not order_number:
        raise HTTPException(status_code=400, detail="merchantOrderId is required in webhook")

    mapping = await get_mapping_by_token_any(order_number)
    if not mapping:
        return {"ok": True}

    await update_status_by_token_any(mapping["rp_token"], provider_status or "unknown")

    callback_payload = {
        "result": _to_rp_result(provider_status),
        "gateway_token": str(platform_id) if platform_id else mapping.get("provider_operation_id"),
        "logs": [],
        "requisites": None
    }

    client = RPCallbackClient()
    try:
        await client.send_callback(mapping["callback_url"], callback_payload)
    except Exception:
        pass

    return {"ok": True}


# ---------- Forta webhook ----------
@router.post("/provider/forta/webhook")
async def forta_webhook(request: Request):
    """
    Ожидаемый callback от Forta:
    {
      "guid": "<gateway_token>",
      "orderId": "ORD123",
      "amount": 1000,
      "status": "PAID|INIT|INPROGRESS|CANCELED",
      "sign": "<md5(orderId + amount + PROVIDER_TOKEN)>"
    }
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    guid = str(payload.get("guid") or "")
    order_id = str(payload.get("orderId") or "")
    amount = str(payload.get("amount") or "")
    status = str(payload.get("status") or "")

    # Проверка подписи, если настроен токен
    prov_token = (settings.FORTA_API_TOKEN or "").strip()
    incoming_sign = str(payload.get("sign") or "")
    if prov_token and incoming_sign:
        check_str = f"{order_id}{amount}{prov_token}"
        calc = hashlib.md5(check_str.encode("utf-8")).hexdigest()
        if calc != incoming_sign:
            raise HTTPException(status_code=401, detail="invalid sign")

    # Ищем маппинг по guid или orderId
    mapping = None
    if guid:
        mapping = await get_mapping_by_token_any(guid)
    if not mapping and order_id:
        mapping = await get_mapping_by_token_any(order_id)
    if not mapping:
        return {"ok": True}

    await update_status_by_token_any(mapping["rp_token"], status or "unknown")

    client = RPCallbackClient()
    callback_payload = {
        "result": _to_rp_result(status),
        "gateway_token": guid or mapping.get("provider_operation_id"),
        "logs": [],
        "requisites": None
    }
    try:
        await client.send_callback(mapping["callback_url"], callback_payload)
    except Exception:
        pass

    return {"ok": True}
