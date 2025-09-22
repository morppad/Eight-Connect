from .brusnika.adapter import BrusnikaAdapter
from .forta.adapter import FortaAdapter

# Инициализируем адаптеры
_registry = {
    "Brusnika_SBP": BrusnikaAdapter(),
    "Forta_SBP_ECOM": FortaAdapter(),
}

# Алиасы имён провайдеров → канонические ключи реестра
_aliases = {
    # Brusnika
    "brusnika": "Brusnika_SBP",
    "brusnika_sbp": "Brusnika_SBP",
    "sbp-brusnika": "Brusnika_SBP",

    # Forta
    "forta": "Forta_SBP_ECOM",
    "forta_sbp": "Forta_SBP_ECOM",
    "forta_sbp_ecom": "Forta_SBP_ECOM",
    "sbp_ecom": "Forta_SBP_ECOM",
}

def get_provider_by_name(name: str | None):
    if not name:
        return None
    key = _aliases.get(name.strip().lower(), name)
    return _registry.get(key)

def resolve_provider_by_payment_method(payment_method: str | None):
    if not payment_method:
        return None
    pm = payment_method.strip().upper()
    # Специфичная логика для SBP_ECOM
    if pm == "SBP_ECOM":
        return _registry.get("Forta_SBP_ECOM")
    # Общая эвристика: всё, что содержит ECOM — к Forta; SBP без ECOM — к Brusnika
    if "ECOM" in pm:
        return _registry.get("Forta_SBP_ECOM")
    if "SBP" in pm:
        return _registry.get("Brusnika_SBP")
    return None
