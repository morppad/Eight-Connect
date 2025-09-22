from fastapi import APIRouter, HTTPException, status, Request
from app.db import update_status_by_token_any, get_mapping_by_token_any
from app.settings import settings
from app.callbacks.rp_client import send_callback_to_rp

router = APIRouter()

ADMIN_SECRET_HEADER = "X-Admin-Secret"
ADMIN_SECRET = "BtdA2653"  # Задайте в .env

@router.post("/admin/update_status")
async def admin_update_status(request: Request, token: str, new_status: str):
    secret = request.headers.get(ADMIN_SECRET_HEADER)
    if secret != ADMIN_SECRET:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    # Обновить статус в БД
    await update_status_by_token_any(token, new_status)
    tx = await get_mapping_by_token_any(token)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    # Отправить коллбек в RP
    await send_callback_to_rp(tx)
    return {"result": "ok", "token": token, "new_status": new_status}
