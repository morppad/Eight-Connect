import json
import httpx
import jwt
from Crypto.Cipher import AES
from base64 import b64encode
from typing import Dict, Any
from app.settings import settings
from ..utils.http import client, retry_policy
from ..settings import settings
from ..utils.security import hmac_sha256_b64


def encrypt_secure_block(data: Dict[str, Any], key: str) -> str:
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    key_bytes = key.encode("utf-8")
    if len(key_bytes) < 32:
        key_bytes = key_bytes.ljust(32, b"\0")  # Дополнение до 32 байт
    else:
        key_bytes = key_bytes[:32]
    iv = b"0" * 16
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
    pad = 16 - len(raw) % 16
    raw += bytes([pad]) * pad
    encrypted = cipher.encrypt(raw)
    return b64encode(encrypted).decode()


def make_jwt(payload: Dict[str, Any], secret: str) -> str:
    return jwt.encode(payload, secret, algorithm="HS512")


async def send_callback_to_rp(tx: dict):
    """
    Отправляет callback в RP по URL из транзакции.
    tx: dict с ключами callback_url, status, rp_token, provider_operation_id и др.
    """
    callback_url = tx.get("callback_url")
    if not callback_url:
        return
    secure_block = {
        "status": tx.get("status"),
        "amount": tx.get("amount"),
        "currency": tx.get("currency"),
        # ... другие поля ...
    }
    encrypted_secure = encrypt_secure_block(secure_block, settings.RP_CALLBACK_SIGNING_SECRET)
    payload = {
        "token": tx.get("rp_token"),
        "gateway_token": tx.get("provider_operation_id"),
        "status": tx.get("status"),
        "currency": tx.get("currency"),
        "amount": tx.get("amount"),
        "secure": encrypted_secure,
        # ... другие поля ...
    }
    jwt_token = make_jwt(payload, settings.RP_CALLBACK_SIGNING_SECRET)
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(callback_url, json=payload, headers=headers)
        print("RP callback response:", resp.status_code, resp.text)


class RPCallbackClient:
    """
    Отправляет коллбеки в RP в формате:
    {
      "result": "approved|declined|pending",
      "gateway_token": "<id>",
      "logs": [],
      "requisites": null
    }
    HMAC-подпись (опционально): заголовок X-RP-Signature (base64(HMAC-SHA256)).
    """

    @retry_policy(max_attempts=settings.RP_CALLBACK_RETRY_MAX)
    async def send_callback(self, url: str, payload: Dict[str, Any]) -> int:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        if settings.RP_CALLBACK_SIGNING_SECRET and settings.RP_CALLBACK_SIGNING_SECRET != "replace_me":
            signature = hmac_sha256_b64(settings.RP_CALLBACK_SIGNING_SECRET, body)
            headers["X-RP-Signature"] = signature

        async with client(timeout_sec=15) as c:
            resp = await c.post(url, content=body, headers=headers)
            resp.raise_for_status()
            return resp.status_code
