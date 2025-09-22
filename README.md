# Gateway Connect — Minimal FastAPI Connector (Brusnika_SBP + Router)

Минимальный, но полноценный коннектор под спецификацию Gateway Connect (ReactivePay), 
с роутером по провайдерам и адаптером под **Brusnika_SBP** (SBP/Host2Host).

## Быстрый старт

```bash
python -m venv .venv && source .venv/bin/activate  # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt

cp .env.example .env  # заполните секреты
mkdir -p data

uvicorn app.main:app --reload --port 8080
```

## Эндпойнты коннектора (RP-facing)

- `POST /pay`
- `POST /payout`
- `POST /refund`
- `POST /status`
- `POST /confirm_secure_code` (заглушка для провайдера без 3DS/OTP)
- `POST /resend_otp` (заглушка)
- `POST /next_payment_step` (заглушка)

## Вебхуки провайдера (Provider-facing)

- `POST /provider/brusnika/webhook` — входящие нотификации статуса от Brusnika.

## Коллбэки в RP

Коннектор отправляет финальные и промежуточные статусы на `callback_url` из запроса RP.
Подпись HMAC-SHA256 (опционально) через `RP_CALLBACK_SIGNING_SECRET` (заголовок `X-RP-Signature`).

## Роутер провайдеров

Провайдер выбирается по полям входа (в приоритете):
1. `settings.provider` (строгое имя провайдера, напр. `Brusnika_SBP`)
2. `params.provider`
3. `payment.paymentMethod` (эвристика)
4. `DEFAULT_PROVIDER` из `.env`

## База данных

SQLite через `aiosqlite` хранит:
- соответствие `rp_token` ↔ `provider` ↔ `provider_operation_id` ↔ `callback_url`,
- идемпотентность по `rp_token`,
- последнюю известную стадию статуса.

## Схемы

- `app/schemas/rp.py` — унифицированные модели RP ↔ Gateway
- `app/schemas/provider/brusnika.py` — модели для Brusnika

## Адаптеры

- `app/providers/brusnika/adapter.py` — реализация `ProviderAdapter` для Brusnika API

## Маршруты

- `app/routers/rp_endpoints.py` — точки входа RP
- `app/routers/provider_webhooks.py` — вебхуки провайдеров

## Лицензия

MIT
