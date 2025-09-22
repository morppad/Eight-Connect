from typing import Protocol, Optional, Dict, Any

class ProviderAdapter(Protocol):
    name: str

    async def pay(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...

    async def status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...

    async def refund(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...

    async def payout(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...

    # В случае отсутствия 3DS/OTP — можно возвращать not_applicable
    async def confirm_secure_code(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...

    async def resend_otp(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...

    async def next_payment_step(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...
