import hmac, hashlib, base64

def hmac_sha256_b64(secret: str, payload: bytes) -> str:
    mac = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).digest()
    return base64.b64encode(mac).decode('utf-8')
