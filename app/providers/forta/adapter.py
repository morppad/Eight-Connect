from typing import Dict, Any, Optional
import httpx
from ...settings import settings
from ...utils.http import client, retry_policy
from ...db import upsert_mapping, get_mapping_by_token_any


class FortaAdapter:
    """
    Forta SBP_ECOM:
      - POST /merchantApic2c/invoice           (создать инвойс)
      - GET  /merchantApic2c/invoice?id={guid} (статус инвойса)
    Возвращаем внешний формат, совместимый с RP UI:
      status="OK", gateway_token, result, requisites, redirectRequest, with_external_format, provider_response_data, logs[]
    """
    name = "Forta_SBP_ECOM"

    def __init__(self):
        self.base_url = (settings.FORTA_BASE_URL or "https://pt.wallet-expert.com").rstrip("/")

    def _api_token(self, payload: Dict[str, Any]) -> str:
        # приоритет: settings.authorization_token из RP-запроса -> ENV
        override = payload.get("_provider_auth")
        return override or settings.FORTA_API_TOKEN

    def _headers(self, token: str) -> Dict[str, str]:
        tok = token.strip()
        # у forta обычно просто значение, без "Bearer "
        return {"Authorization": tok, "Content-Type": "application/json"}

    # ---- status map ----
    def _status_map(self, s: Optional[str]) -> str:
        sl = (s or "").upper()
        if sl in {"PAID", "SUCCESS", "CONFIRMED"}:
            return "approved"
        if sl in {"CANCELED", "CANCELLED", "FAILED", "DECLINED", "ERROR"}:
            return "declined"
        return "pending"  # INIT, INPROGRESS, CREATED, ...

    @retry_policy()
    async def _post(self, path: str, json_payload: Dict[str, Any], token: str) -> httpx.Response:
        async with client() as c:
            return await c.post(f"{self.base_url}{path}", json=json_payload, headers=self._headers(token))

    @retry_policy()
    async def _get(self, path: str, token: str) -> httpx.Response:
        async with client() as c:
            return await c.get(f"{self.base_url}{path}", headers=self._headers(token))

    # ---- build requisites & provider_response_data ----
    def _build_output(self, data_block: Dict[str, Any], payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Forta в ответе присылает:
          data.guid, data.qrCodeLink, data.status, data.receiverName, data.receiverBank, data.receiverPhone ...
        Формируем:
          - requisites: LINK (если есть qrCodeLink) + holder/bank_name
          - provider_response_data: для gateway_details.provider_response_data
        """
        link = data_block.get("qrCodeLink") or data_block.get("link") or None
        holder = data_block.get("receiverName") or ""
        bank_name = data_block.get("receiverBank") or ""
        phone = str(data_block.get("receiverPhone") or "")

        # Проверяем флаг wrapped_to_json для H2H формата
        wrapped_to_json = payload and payload.get("wrapped_to_json") == True

        if link:
            if wrapped_to_json:
                # H2H JSON формат - встраиваем QR как JSON объект
                requisites = {
                    "qr_data": {
                        "type": "sbp_ecom",
                        "qr_url": link,
                        "embedded_json": True
                    },
                    "holder": holder,
                    "bank_name": bank_name,
                    "phone": phone
                }
            else:
                # Стандартный формат со ссылкой
                requisites = {
                    "link": {"url": link},
                    "holder": holder,
                    "bank_name": bank_name
                }
        else:
            # запасной вариант: если нет ссылки — хотя бы реквизиты SBP по телефону
            requisites = {
                "pan": phone,
                "holder": holder,
                "bank_name": bank_name
            } if phone else {}

        provider_response_data = {
            "guid": data_block.get("guid"),
            "orderId": data_block.get("orderId"),
            "amount": data_block.get("amount"),
            "bank": data_block.get("bank"),
            "status": data_block.get("status"),
            "qrCodeLink": link,
            "receiverName": holder,
            "receiverBank": bank_name,
            "receiverPhone": phone,
            "wrapped_to_json": wrapped_to_json
        }
        return {"requisites": requisites, "provider_response_data": provider_response_data}

    # ---- Adapter API ----
    async def pay(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        token = self._api_token(payload)

        # Готовим тело запроса в Forta
        body = {
            "orderId": payload["order_number"],
            "amount": int(payload["amount"]),
            "bank": "SBP_ECOM",
            "payerHash": (payload.get("customer") or {}).get("client_id") or payload.get("rp_token"),
            # На Forta должен указывать вебхук вашего коннектора, а не RP:
            "callbackUrl": settings.FORTA_WEBHOOK_URL or f"{settings.PUBLIC_BASE_URL.rstrip('/')}/provider/forta/webhook",
            "returnUrl": payload.get("redirect_success_url") or payload.get("processing_url") or settings.PUBLIC_BASE_URL
        }

        logs = [{
            "gateway": "forta",
            "request": {"url": "/merchantApic2c/invoice", "params": {**body, "callbackUrl": "***"}},
            "status": None,
            "response": None,
            "kind": "pay",
        }]

        try:
            resp = await self._post("/merchantApic2c/invoice", json_payload=body, token=token)
            try:
                js = resp.json()
            except Exception:
                js = {"raw_text": resp.text or ""}
            logs[-1]["status"] = resp.status_code
            logs[-1]["response"] = js
        except Exception as e:
            logs[-1]["status"] = 599
            logs[-1]["response"] = {"error": str(e)}
            return {
                "status": "OK",
                "gateway_token": None,
                "result": "declined",
                "requisites": {},
                "redirectRequest": {"url": None, "type": "post_iframes", "iframes": []},
                "with_external_format": True,
                "provider_response_data": {},
                "logs": logs,
            }

        data_block = js.get("data") or {}
        provider_status = data_block.get("status") or (js.get("result") or {}).get("status")
        result_norm = self._status_map(provider_status)
        gateway_token = str(data_block.get("guid") or "")

        # Сохраняем маппинг для статусов/вебхуков
        await upsert_mapping(
            rp_token=payload["rp_token"],
            order_number=payload["order_number"],
            provider=self.name,
            callback_url=payload["callback_url"],
            provider_operation_id=gateway_token,
            status=provider_status,
        )

        built = self._build_output(data_block, payload)
        requisites = built["requisites"]
        provider_response_data = built["provider_response_data"]

        # редирект: настраиваем на основе параметров
        redirect_request = {"url": None, "type": "post_iframes", "iframes": []}
        qr_link = provider_response_data.get("qrCodeLink")

        if qr_link:
            # Проверяем флаг для отображения QR на нашей форме
            show_on_form = payload.get("show_qr_on_form") == True
            wrapped_to_json = payload.get("wrapped_to_json") == True

            if show_on_form:
                # Task 2: QR на нашей форме через iframe - используем наш собственный endpoint
                form_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/qr_form/{gateway_token}"
                redirect_request = {
                    "url": form_url,
                    "type": "post_iframes",
                    "iframes": [
                        {
                            "url": form_url,
                            "data": {
                                "gateway_token": gateway_token,
                                "qr_url": qr_link,
                                "amount": payload.get("amount"),
                                "currency": payload.get("currency", "RUB"),
                                "order_number": payload.get("order_number")
                            }
                        }
                    ]
                }
            elif wrapped_to_json:
                # Task 1: H2H JSON формат - не используем redirect, QR встроен в requisites
                redirect_request = {"url": None, "type": "json_embedded", "iframes": []}
            else:
                # Стандартный redirect на QR ссылку
                redirect_request = {"url": qr_link, "type": "redirect", "iframes": []}

        return {
            "status": "OK",
            "gateway_token": gateway_token or None,
            "result": result_norm,
            "requisites": requisites,
            "redirectRequest": redirect_request,
            "with_external_format": True,
            "provider_response_data": provider_response_data,
            "logs": logs,
        }

    async def status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        token = self._api_token(payload)
        # ищем guid: сначала из входа, иначе по маппингу
        key = payload.get("gateway_token") or payload.get("rp_token") or payload.get("order_number")
        mapping = await get_mapping_by_token_any(key) if key else None
        if not mapping or not mapping.get("provider_operation_id"):
            return {
                "result": "OK",
                "status": "pending",
                "details": "no guid in mapping",
                "amount": None,
                "currency": None,
                "logs": [],
                "with_external_format": True,
                "provider_response_data": {},
                "requisites": {}
            }

        guid = mapping["provider_operation_id"]

        logs = [{
            "gateway": "forta",
            "request": {"url": "/merchantApic2c/invoice", "params": {"id": guid}},
            "status": None,
            "response": None,
            "kind": "status",
        }]

        try:
            resp = await self._get(f"/merchantApic2c/invoice?id={guid}", token=token)
            try:
                js = resp.json()
            except Exception:
                js = {"raw_text": resp.text or ""}
            logs[-1]["status"] = resp.status_code
            logs[-1]["response"] = js
        except Exception as e:
            logs[-1]["status"] = 599
            logs[-1]["response"] = {"error": str(e)}
            return {
                "result": "OK",
                "status": "pending",
                "details": f"Gateway unreachable: {e}",
                "amount": None,
                "currency": None,
                "logs": logs,
                "with_external_format": True,
                "provider_response_data": {},
                "requisites": {}
            }

        data_block = js.get("data") or {}
        provider_status = data_block.get("status") or (js.get("result") or {}).get("status")
        status_norm = self._status_map(provider_status)

        built = self._build_output(data_block, payload)

        # по возможности отдадим сумму/валюту
        amount = data_block.get("amount")
        currency = data_block.get("currency") or "RUB"

        return {
            "result": "OK",
            "status": status_norm,
            "details": f"Transaction status: {status_norm}",
            "amount": amount,
            "currency": currency,
            "logs": logs,
            "with_external_format": True,
            "provider_response_data": built["provider_response_data"],
            "requisites": built["requisites"],
        }

    async def refund(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "result": "ERROR",
            "status": "declined",
            "details": "Refund not supported by Forta SBP_ECOM",
            "amount": None,
            "currency": None,
            "logs": [],
        }

    async def payout(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "result": "ERROR",
            "status": "declined",
            "details": "Payout not implemented for Forta SBP_ECOM",
            "amount": None,
            "currency": None,
            "logs": [],
        }
