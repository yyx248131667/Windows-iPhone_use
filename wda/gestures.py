import logging
from typing import Any, Dict, Optional
from .client import WDAClient
from .session import WDASession

logger = logging.getLogger(__name__)


class WDAGestures:
    """
    Implements touch interactions, gestures, hardware key actions, and app control.
    """

    def __init__(self, client: WDAClient, session: WDASession):
        self.client = client
        self.session = session

    def tap(self, x: float, y: float) -> Dict[str, Any]:
        """Tap at screen coordinate (x, y)."""
        sid = self.session.ensure_session()
        payload = {"x": x, "y": y}
        return self.client.post(f"/session/{sid}/wda/tap/nil", json_data=payload)

    def double_tap(self, x: float, y: float) -> Dict[str, Any]:
        """Double tap at (x, y)."""
        sid = self.session.ensure_session()
        payload = {"x": x, "y": y}
        return self.client.post(f"/session/{sid}/wda/doubleTap", json_data=payload)

    def long_press(self, x: float, y: float, duration: float = 1.0) -> Dict[str, Any]:
        """Press and hold at (x, y) for given duration."""
        sid = self.session.ensure_session()
        payload = {"x": x, "y": y, "duration": duration}
        return self.client.post(f"/session/{sid}/wda/touchAndHold", json_data=payload)

    def swipe(self, from_x: float, from_y: float, to_x: float, to_y: float, duration: float = 0.5) -> Dict[str, Any]:
        """Drag / swipe from coordinate A to coordinate B."""
        sid = self.session.ensure_session()
        payload = {
            "fromX": from_x,
            "fromY": from_y,
            "toX": to_x,
            "toY": to_y,
            "duration": duration,
        }
        return self.client.post(f"/session/{sid}/wda/dragfromtoforduration", json_data=payload)

    def scroll(self, direction: str = "down") -> Dict[str, Any]:
        """
        Scroll screen in specified direction ('up', 'down', 'left', 'right').
        """
        sid = self.session.ensure_session()
        return self.client.post(f"/session/{sid}/wda/scroll", json_data={"direction": direction})

    def send_keys(self, text: str) -> Dict[str, Any]:
        """Type text into currently focused element or keyboard."""
        sid = self.session.ensure_session()
        return self.client.post(f"/session/{sid}/wda/keys", json_data={"value": list(text)})

    def press_home(self) -> Dict[str, Any]:
        """Press device Home button (or swipe up to return to SpringBoard)."""
        return self.client.post("/wda/homescreen")

    def lock(self) -> Dict[str, Any]:
        """Lock device screen."""
        return self.client.post("/wda/lock")

    def unlock(self) -> Dict[str, Any]:
        """Unlock device screen."""
        return self.client.post("/wda/unlock")

    def is_locked(self) -> bool:
        """Check if screen is currently locked."""
        res = self.client.get("/wda/locked")
        return bool(res.get("value"))

    def launch_app(self, bundle_id: str, arguments: Optional[list] = None, environment: Optional[dict] = None) -> Dict[str, Any]:
        """Launch an application on device by its Bundle ID."""
        sid = self.session.ensure_session()
        payload = {
            "bundleId": bundle_id,
            "arguments": arguments or [],
            "environment": environment or {},
        }
        return self.client.post(f"/session/{sid}/wda/apps/launch", json_data=payload)

    def terminate_app(self, bundle_id: str) -> Dict[str, Any]:
        """Terminate a running application by Bundle ID."""
        sid = self.session.ensure_session()
        return self.client.post(f"/session/{sid}/wda/apps/terminate", json_data={"bundleId": bundle_id})

    def app_state(self, bundle_id: str) -> int:
        """
        Get state of application.
        1: Not running, 2: Running in background/suspended, 3: Running in background, 4: Running in foreground
        """
        sid = self.session.ensure_session()
        res = self.client.post(f"/session/{sid}/wda/apps/state", json_data={"bundleId": bundle_id})
        return res.get("value", 0)
