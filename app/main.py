from fastapi import FastAPI
from .settings import settings
from .routers import rp_endpoints, provider_webhooks, admin

app = FastAPI(title=settings.APP_NAME)

app.include_router(rp_endpoints.router, tags=["ReactivePay"])
app.include_router(provider_webhooks.router, tags=["Provider Webhooks"])
app.include_router(admin.router)

@app.get("/health", tags=["Ops"])
async def health():
    return {"status": "ok"}
