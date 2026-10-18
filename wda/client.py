import logging
import time
from typing import Any, Dict, Optional
import requests

logger = logging.getLogger(__name__)


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

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.request(
                    method=method,
                    url=url,
                    json=json_data,
                    timeout=self.timeout,
                    **kwargs,
                )
                
                # Check for WDA error payload
                if resp.status_code >= 400:
                    logger.warning(f"HTTP {resp.status_code} on {method} {url}: {resp.text[:200]}")
                
                try:
                    return resp.json()
                except ValueError:
                    return {"statusCode": resp.status_code, "raw": resp.text}

            except requests.RequestException as e:
                last_exception = e
                logger.warning(f"Attempt {attempt}/{self.max_retries} failed on {method} {url}: {e}")
                if attempt < self.max_retries:
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
        """Check if WDA is responsive."""
        try:
            res = self.status()
            return res.get("value", {}).get("state") == "success" or "sessionId" in str(res) or res.get("status") == 0
        except Exception:
            return False
