import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

def client(timeout_sec: int = 15) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout_sec)

def retry_policy(max_attempts: int = 4):
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        retry=retry_if_exception_type(httpx.HTTPError)
    )
