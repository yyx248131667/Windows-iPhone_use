import logging
from typing import Any, Dict, Optional, Tuple
from .client import WDAClient

logger = logging.getLogger(__name__)


class WDASession:
    """
    Manages an active WebDriverAgent test session.
    """

    def __init__(self, client: WDAClient, session_id: Optional[str] = None):
        self.client = client
        self.session_id = session_id
        self._window_size: Optional[Tuple[int, int]] = None

    def start(self, capabilities: Optional[Dict[str, Any]] = None) -> str:
        """Create a new session on WDA."""
        payload = {
            "capabilities": {
                "firstMatch": [capabilities or {}]
            }
        }
        res = self.client.post("/session", json_data=payload)
        self.session_id = res.get("sessionId") or res.get("value", {}).get("sessionId")
        if not self.session_id:
            raise RuntimeError(f"Failed to create WDA session: {res}")
        logger.info(f"Started WDA session: {self.session_id}")
        return self.session_id

    def close(self) -> None:
        """Terminate the active session."""
        if self.session_id:
            try:
                self.client.delete(f"/session/{self.session_id}")
                logger.info(f"Closed WDA session: {self.session_id}")
            except Exception as e:
                logger.warning(f"Error closing session {self.session_id}: {e}")
            finally:
                self.session_id = None

    def ensure_session(self) -> str:
        """Ensure an active session exists, creating one if necessary."""
        if not self.session_id:
            self.start()
        return self.session_id

    def get_window_size(self) -> Tuple[int, int]:
        """Fetch screen dimensions (width, height) in points."""
        sid = self.ensure_session()
        res = self.client.get(f"/session/{sid}/window/size")
        val = res.get("value", {})
        width = int(val.get("width", 0))
        height = int(val.get("height", 0))
        self._window_size = (width, height)
        return self._window_size

    def __enter__(self):
        self.ensure_session()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
