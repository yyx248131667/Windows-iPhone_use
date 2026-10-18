import logging
import time
from typing import Any, Dict, Optional, Tuple
from PIL import Image

from device.discovery import DeviceDiscovery, DeviceInfo
from device.pairing import DevicePairing
from device.tunnel import TunnelManager
from device.wda_runner import WDARunner
from wda.client import WDAClient
from wda.session import WDASession
from wda.screenshot import WDAScreenshot
from wda.elements import WDAElements
from wda.gestures import WDAGestures
from .actions import (
    ActionType,
    BaseAction,
    TapAction,
    DoubleTapAction,
    LongPressAction,
    SwipeAction,
    ScrollAction,
    InputAction,
    LaunchAppAction,
    TerminateAppAction,
    WaitAction,
)

logger = logging.getLogger(__name__)


class iPhoneController:
    """
    Unified high-level automation controller for iPhone on Windows.
    Coordinates device discovery, iOS 17+ tunnel, XCTest WDA runner, and interactions.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        go_ios_bin: str = "ios",
        udid: Optional[str] = None,
        wda_base_url: str = "http://127.0.0.1:8100",
    ):
        self.config = config or {}
        dev_cfg = self.config.get("device", {})
        tool_cfg = self.config.get("tools", {})
        wda_cfg = self.config.get("wda", {})
        tunnel_cfg = self.config.get("tunnel", {})

        self.go_ios_bin = tool_cfg.get("go_ios_bin", go_ios_bin)
        self.udid = udid or dev_cfg.get("udid")
        self.bundle_id = dev_cfg.get("bundle_id", "com.facebook.WebDriverAgentRunner.xctrunner")
        self.testrunner_bundle_id = dev_cfg.get("testrunner_bundle_id", "com.facebook.WebDriverAgentRunner.xctrunner")
        self.xctestrun_path = dev_cfg.get("xctestrun_path")
        self.wda_base_url = wda_cfg.get("base_url", wda_base_url)

        self.device_info: Optional[DeviceInfo] = None
        self.discovery = DeviceDiscovery(go_ios_bin=self.go_ios_bin)
        self.pairing = DevicePairing(go_ios_bin=self.go_ios_bin, udid=self.udid)
        self.tunnel: Optional[TunnelManager] = None
        self.wda_runner: Optional[WDARunner] = None

        self.client = WDAClient(base_url=self.wda_base_url)
        self.session = WDASession(client=self.client)
        self.screenshot = WDAScreenshot(client=self.client)
        self.elements = WDAElements(client=self.client, session=self.session)
        self.gestures = WDAGestures(client=self.client, session=self.session)

    def initialize(self, auto_start_tunnel: bool = True, auto_start_wda: bool = True) -> Tuple[bool, str]:
        """
        Verify complete pipeline:
        1. Discover device
        2. Setup iOS 17+ tunnel if needed
        3. Start WDA runner if needed
        4. Initialize WDA session
        """
        logger.info("Initializing iPhone controller pipeline...")

        # 1. Device discovery
        self.device_info = self.discovery.get_default_device(self.udid)
        if not self.device_info:
            return False, "No connected iPhone detected. Please connect your iPhone via USB and unlock the screen."
        
        self.udid = self.device_info.udid
        logger.info(f"Target device: {self.device_info.device_name} (UDID: {self.udid}, iOS: {self.device_info.product_version})")

        # 2. Check pairing
        paired, pair_msg = self.pairing.check_and_pair()
        logger.info(f"Device pairing status: {paired} ({pair_msg})")

        # 3. Setup Tunnel if iOS 17+ or requested
        if auto_start_tunnel:
            self.tunnel = TunnelManager(
                go_ios_bin=self.go_ios_bin,
                udid=self.udid,
                ios_version=self.device_info.product_version,
            )
            ok, msg = self.tunnel.start_tunnel()
            logger.info(f"Tunnel status: {ok} ({msg})")

        # 4. Check if WDA is already responding
        if self.client.is_ready():
            logger.info("WDA is already online and responding.")
        elif auto_start_wda:
            logger.info("WDA not responding. Launching WDA runner via XCTest...")
            self.wda_runner = WDARunner(
                go_ios_bin=self.go_ios_bin,
                udid=self.udid,
                bundle_id=self.bundle_id,
                testrunner_bundle_id=self.testrunner_bundle_id,
                xctestrun_path=self.xctestrun_path,
                wda_base_url=self.wda_base_url,
            )
            started, run_msg = self.wda_runner.start(timeout_seconds=35)
            if not started:
                return False, f"Failed to start WDA runner: {run_msg}"

        # 5. Ensure Session
        try:
            self.session.ensure_session()
            size = self.session.get_window_size()
            logger.info(f"WDA session active. Screen dimensions: {size[0]}x{size[1]}")
            return True, f"iPhone controller initialized successfully. Screen: {size[0]}x{size[1]}"
        except Exception as e:
            return False, f"Connected to WDA but session initialization failed: {e}"

    def execute_action(self, action: BaseAction) -> Dict[str, Any]:
        """Execute a typed automation action."""
        t = action.action_type
        if t == ActionType.TAP:
            act: TapAction = action  # type: ignore
            return self.gestures.tap(act.x, act.y)
        elif t == ActionType.DOUBLE_TAP:
            act: DoubleTapAction = action  # type: ignore
            return self.gestures.double_tap(act.x, act.y)
        elif t == ActionType.LONG_PRESS:
            act: LongPressAction = action  # type: ignore
            return self.gestures.long_press(act.x, act.y, act.duration)
        elif t == ActionType.SWIPE:
            act: SwipeAction = action  # type: ignore
            return self.gestures.swipe(act.from_x, act.from_y, act.to_x, act.to_y, act.duration)
        elif t == ActionType.SCROLL:
            act: ScrollAction = action  # type: ignore
            return self.gestures.scroll(act.direction)
        elif t == ActionType.INPUT_TEXT:
            act: InputAction = action  # type: ignore
            return self.gestures.send_keys(act.text)
        elif t == ActionType.PRESS_HOME:
            return self.gestures.press_home()
        elif t == ActionType.LOCK:
            return self.gestures.lock()
        elif t == ActionType.UNLOCK:
            return self.gestures.unlock()
        elif t == ActionType.LAUNCH_APP:
            act: LaunchAppAction = action  # type: ignore
            return self.gestures.launch_app(act.bundle_id)
        elif t == ActionType.TERMINATE_APP:
            act: TerminateAppAction = action  # type: ignore
            return self.gestures.terminate_app(act.bundle_id)
        elif t == ActionType.SCREENSHOT:
            return {"base64": self.screenshot.get_base64()}
        elif t == ActionType.WAIT:
            act: WaitAction = action  # type: ignore
            time.sleep(act.seconds)
            return {"status": "waited", "seconds": act.seconds}
        else:
            raise ValueError(f"Unsupported action type: {t}")

    def capture_screenshot(self) -> Image.Image:
        return self.screenshot.get_image()

    def capture_screenshot_base64(self) -> str:
        return self.screenshot.get_base64()

    def get_ui_hierarchy(self) -> Any:
        return self.elements.get_source()

    def shutdown(self) -> None:
        """Tear down active sessions, WDA runner, and tunnel."""
        logger.info("Shutting down iPhone controller...")
        try:
            self.session.close()
        except Exception:
            pass
        if self.wda_runner:
            self.wda_runner.stop()
        if self.tunnel:
            self.tunnel.stop_tunnel()
