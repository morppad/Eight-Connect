from pydantic import BaseModel
from typing import Optional, Any, Dict, List

# Упрощенные модели для примера адаптера.
# В реальной интеграции следует отразить поля из OpenAPI полностью.

class PayInRequest(BaseModel):
    # пример: поля для Host2Host/SBP (упрощено)
    amount: int
    currency: str
    merchantOrderId: str
    description: Optional[str] = None
    customerPhone: Optional[str] = None
    customerEmail: Optional[str] = None

class PayInResponse(BaseModel):
    success: bool
    platformOperationId: Optional[str] = None
    qrLink: Optional[str] = None
    deeplink: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

class StatusResponse(BaseModel):
    success: bool
    platformOperationId: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None
