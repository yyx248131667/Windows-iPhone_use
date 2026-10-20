import logging
import time
from typing import Any, Dict, Optional
import requests

logger = logging.getLogger(__name__)


class WDAError(RuntimeError):
    """A WDA HTTP or protocol error, which must not be reported as success."""

    def __init__(self, message, status_code=None, error=None):
        super().__init__(message)
        self.status_code = status_code
        self.error = error


class WDAClient:
    """
    HTTP client for WebDriverAgent RESTful API.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8100", timeout: float = 30.0, max_retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def request(self, method: str, path: str, json_data: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        url = self._url(path)
        last_exception = None

        timeout = kwargs.pop("timeout", self.timeout)
        attempts = kwargs.pop("max_retries", self.max_retries if method.upper() == "GET" else 1)
        for attempt in range(1, attempts + 1):
            try:
                resp = self.session.request(
                    method=method,
                    url=url,
                    json=json_data,
                    timeout=timeout,
                    **kwargs,
                )
                
                # Check for WDA error payload
                if resp.status_code >= 400:
                    logger.warning(f"HTTP {resp.status_code} on {method} {url}: {resp.text[:200]}")
                
                try:
                    data = resp.json()
                except ValueError:
                    raise WDAError(f"WDA returned HTTP {resp.status_code}: {resp.text[:200]}")
                value = data.get("value")
                error = value.get("error") if isinstance(value, dict) else None
                if resp.status_code >= 400 or error or data.get("status", 0) not in (0, None):
                    message = value.get("message", error) if isinstance(value, dict) else str(value)
                    raise WDAError(f"WDA HTTP {resp.status_code}: {message}", resp.status_code, error)
                return data

            except requests.RequestException as e:
                last_exception = e
                logger.warning(f"Attempt {attempt}/{attempts} failed on {method} {url}: {e}")
                if attempt < attempts:
                    time.sleep(1.0)

        raise ConnectionError(f"Failed to connect to WDA at {url}: {last_exception}")

    def get(self, path: str, **kwargs) -> Dict[str, Any]:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, json_data: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        return self.request("POST", path, json_data=json_data, **kwargs)

    def delete(self, path: str, **kwargs) -> Dict[str, Any]:
        return self.request("DELETE", path, **kwargs)

    def status(self) -> Dict[str, Any]:
        """Fetch WDA server status."""
        return self.get("/status")

    def is_ready(self) -> bool:
        """Check if WDA is responsive without retrying or polluting logs."""
        try:
            resp = self.session.get(self._url("/status"), timeout=1.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("value", {}).get("state") == "success" or "sessionId" in str(data) or data.get("status") == 0
            return False
        except Exception:
            return False
