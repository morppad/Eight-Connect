from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List


# ====== ВХОД ОТ RP (вложенный формат) ======

class RPCustomer(BaseModel):
    client_id: Optional[str] = None
    client_ip: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class RPSettings(BaseModel):
    provider: Optional[str] = None
    authorization_token: Optional[str] = None  # токен провайдера на один вызов
    model_config = {"extra": "allow"}


class RPParams(BaseModel):
    customer: Optional[RPCustomer] = None
    model_config = {"extra": "allow"}


class RPPayment(BaseModel):
    token: str
    product: Optional[str] = None
    order_number: str
    amount: int
    gateway_amount: Optional[int] = None
    currency: str
    redirect_success_url: Optional[str] = None
    redirect_fail_url: Optional[str] = None
    paymentMethod: Optional[str] = None  # на всякий случай
    model_config = {"extra": "allow"}


class RPNestedPayRequest(BaseModel):
    settings: Optional[RPSettings] = None
    params: Optional[RPParams] = None
    payment: RPPayment
    processing_url: Optional[str] = None
    callback_url: str
    callback_3ds_url: Optional[str] = None
    method_name: Optional[str] = None
    model_config = {"extra": "allow"}


# ====== ВЫХОД К RP ======

class RedirectRequest(BaseModel):
    method: str
    url: str
    headers: Optional[Dict[str, str]] = None
    body: Optional[Any] = None


class RPResponse(BaseModel):
    # Стандарт RP для Gateway Connect (P2P/E-Com)
    result: str = Field(description="approved | declined | pending")
    gateway_token: Optional[str] = None
    redirect_request: Optional[RedirectRequest] = None
    requisites: Optional[Dict[str, Any]] = None
    logs: Optional[List[Dict[str, Any]]] = None
    message: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None
