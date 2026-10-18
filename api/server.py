import io
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional
import yaml
from fastapi import FastAPI, HTTPException, Query, Response, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.controller import iPhoneController
from agent.actions import (
    BaseAction,
    TapAction,
    SwipeAction,
    InputAction,
    LaunchAppAction,
    TerminateAppAction,
    parse_action,
)
from device.discovery import DeviceDiscovery, DeviceInfo

logger = logging.getLogger(__name__)

# In-memory log buffer for WebUI live console
log_records: List[Dict[str, Any]] = []
MAX_LOG_RECORDS = 200


class WebUILogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            log_records.append({
                "time": time.strftime("%H:%M:%S", time.localtime(record.created)),
                "level": record.levelname,
                "name": record.name,
                "message": msg,
            })
            if len(log_records) > MAX_LOG_RECORDS:
                del log_records[0 : len(log_records) - MAX_LOG_RECORDS]
        except Exception:
            pass


root_logger = logging.getLogger()
web_handler = WebUILogHandler()
web_handler.setFormatter(logging.Formatter("%(message)s"))
root_logger.addHandler(web_handler)

app = FastAPI(
    title="Windows-iPhone_use WebUI & API",
    description="WebUI and API service for controlling iPhone via WebDriverAgent on Windows",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global controller instance and pipeline state
controller: Optional[iPhoneController] = None
pipeline_state = {
    "status": "idle",  # idle, running, error, success
    "current_step": "",
    "error_message": "",
    "steps": {
        "discovery": "pending",
        "pairing": "pending",
        "tunnel": "pending",
        "wda": "pending",
        "session": "pending",
    },
}


def get_controller() -> iPhoneController:
    global controller
    if controller is None:
        cfg = {}
        try:
            if os.path.exists("config/settings.yaml"):
                with open("config/settings.yaml", "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to load config/settings.yaml: {e}")
        controller = iPhoneController(config=cfg)
    return controller


# -------------------------------------------------------------
# WebUI Page
# -------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index_page():
    html_file = os.path.join(os.path.dirname(__file__), "..", "web", "index.html")
    if os.path.exists(html_file):
        with open(html_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>WebUI file not found. Please ensure web/index.html exists.</h2>")


# -------------------------------------------------------------
# Status & Pipeline Endpoints
# -------------------------------------------------------------
@app.get("/api/status/all")
def get_all_status():
    ctrl = get_controller()
    
    # 1. Device status
    device_data = None
    if ctrl.device_info:
        device_data = ctrl.device_info.to_dict()
    else:
        # Quick check if any device is connected
        devs = ctrl.discovery.list_devices()
        if devs:
            ctrl.device_info = devs[0]
            device_data = devs[0].to_dict()

    # 2. Tunnel status
    tunnel_alive = ctrl.tunnel.is_alive() if ctrl.tunnel else False

    # 3. WDA status
    wda_online = ctrl.client.is_ready()

    # 4. Session status & Screen Size
    session_active = bool(ctrl.session.session_id)
    screen_width, screen_height = 390, 844  # default standard fallback
    if session_active or wda_online:
        try:
            size = ctrl.session.get_window_size()
            if size and size[0] > 0 and size[1] > 0:
                screen_width, screen_height = size[0], size[1]
                session_active = True
        except Exception:
            pass

    return {
        "device": device_data,
        "tunnel": {
            "alive": tunnel_alive,
            "required": device_data.get("is_ios_17_plus", True) if device_data else True,
        },
        "wda": {
            "online": wda_online,
            "base_url": ctrl.wda_base_url,
        },
        "session": {
            "active": session_active,
            "session_id": ctrl.session.session_id,
            "screen_size": {"width": screen_width, "height": screen_height},
        },
        "pipeline": pipeline_state,
    }


def _run_pipeline_worker():
    global pipeline_state
    ctrl = get_controller()
    pipeline_state["status"] = "running"
    pipeline_state["error_message"] = ""

    # Step 1: Discovery
    pipeline_state["current_step"] = "正在探测已连接的 iPhone..."
    pipeline_state["steps"]["discovery"] = "running"
    dev = ctrl.discovery.get_default_device(ctrl.udid)
    if not dev:
        pipeline_state["status"] = "error"
        pipeline_state["steps"]["discovery"] = "failed"
        pipeline_state["error_message"] = "未检测到 USB 连接的 iPhone。请插好数据线并解锁屏幕。"
        return
    ctrl.device_info = dev
    ctrl.udid = dev.udid
    pipeline_state["steps"]["discovery"] = "success"

    # Step 2: Pairing
    pipeline_state["current_step"] = "检查设备配对与信任状态..."
    pipeline_state["steps"]["pairing"] = "running"
    paired, pair_msg = ctrl.pairing.check_and_pair()
    if not paired:
        pipeline_state["status"] = "error"
        pipeline_state["steps"]["pairing"] = "failed"
        pipeline_state["error_message"] = f"设备配对失败: {pair_msg}"
        return
    pipeline_state["steps"]["pairing"] = "success"

    # Step 3: Tunnel
    pipeline_state["current_step"] = "建立通信隧道 (iOS 17+ CoreDevice)..."
    pipeline_state["steps"]["tunnel"] = "running"
    from device.tunnel import TunnelManager
    if not ctrl.tunnel or not ctrl.tunnel.is_alive():
        ctrl.tunnel = TunnelManager(
            go_ios_bin=ctrl.go_ios_bin,
            udid=ctrl.udid,
            ios_version=dev.product_version,
        )
        ok, t_msg = ctrl.tunnel.start_tunnel()
        if not ok:
            pipeline_state["status"] = "error"
            pipeline_state["steps"]["tunnel"] = "failed"
            pipeline_state["error_message"] = f"隧道启动失败: {t_msg}"
            return
    pipeline_state["steps"]["tunnel"] = "success"

    # Step 4: WDA Runner
    pipeline_state["current_step"] = "启动 WebDriverAgent (XCTest)..."
    pipeline_state["steps"]["wda"] = "running"
    if not ctrl.client.is_ready():
        from device.wda_runner import WDARunner
        ctrl.wda_runner = WDARunner(
            go_ios_bin=ctrl.go_ios_bin,
            udid=ctrl.udid,
            bundle_id=ctrl.bundle_id,
            testrunner_bundle_id=ctrl.testrunner_bundle_id,
            xctestrun_path=ctrl.xctestrun_path,
            wda_base_url=ctrl.wda_base_url,
        )
        started, run_msg = ctrl.wda_runner.start(timeout_seconds=45)
        if not started:
            pipeline_state["status"] = "error"
            pipeline_state["steps"]["wda"] = "failed"
            pipeline_state["error_message"] = f"WDA 启动失败: {run_msg}"
            return
    pipeline_state["steps"]["wda"] = "success"

    # Step 5: Session
    pipeline_state["current_step"] = "初始化测试会话并同步屏幕..."
    pipeline_state["steps"]["session"] = "running"
    try:
        ctrl.session.ensure_session()
        size = ctrl.session.get_window_size()
        pipeline_state["steps"]["session"] = "success"
        pipeline_state["status"] = "success"
        pipeline_state["current_step"] = f"全流程启动成功！分辨率: {size[0]}x{size[1]}"
    except Exception as e:
        pipeline_state["status"] = "error"
        pipeline_state["steps"]["session"] = "failed"
        pipeline_state["error_message"] = f"会话初始化异常: {e}"


@app.post("/api/pipeline/start")
def start_pipeline(bg_tasks: BackgroundTasks):
    global pipeline_state
    if pipeline_state["status"] == "running":
        return {"status": "running", "message": "Pipeline is already executing."}
    
    pipeline_state = {
        "status": "running",
        "current_step": "准备启动全流程自动化...",
        "error_message": "",
        "steps": {
            "discovery": "pending",
            "pairing": "pending",
            "tunnel": "pending",
            "wda": "pending",
            "session": "pending",
        },
    }
    bg_tasks.add_task(_run_pipeline_worker)
    return {"status": "started", "message": "Pipeline initiated in background."}


@app.post("/api/pipeline/stop")
def stop_pipeline():
    global pipeline_state
    ctrl = get_controller()
    ctrl.shutdown()
    pipeline_state["status"] = "idle"
    pipeline_state["current_step"] = "所有服务已停止"
    for k in pipeline_state["steps"]:
        pipeline_state["steps"][k] = "pending"
    return {"success": True, "message": "Pipeline and services stopped."}


# -------------------------------------------------------------
# Screen Mirroring & Capture
# -------------------------------------------------------------
@app.get("/api/screen/latest")
def get_screen_latest():
    ctrl = get_controller()
    if not ctrl.client.is_ready():
        return {"success": False, "message": "WDA is offline"}
    try:
        b64 = ctrl.capture_screenshot_base64()
        return {"success": True, "base64": b64}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/api/screen/raw")
def get_screen_raw():
    ctrl = get_controller()
    try:
        raw_bytes = ctrl.screenshot.get_bytes()
        return Response(content=raw_bytes, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------
# Interactive Touch & Actions
# -------------------------------------------------------------
class TapRequest(BaseModel):
    x: Optional[float] = None
    y: Optional[float] = None
    normalized_x: Optional[float] = None  # 0.0 - 1.0
    normalized_y: Optional[float] = None  # 0.0 - 1.0


@app.post("/api/action/tap")
def action_tap(req: TapRequest):
    ctrl = get_controller()
    tx, ty = req.x, req.y

    if req.normalized_x is not None and req.normalized_y is not None:
        try:
            width, height = ctrl.session.get_window_size()
        except Exception:
            width, height = 390, 844
        tx = req.normalized_x * width
        ty = req.normalized_y * height

    if tx is None or ty is None:
        raise HTTPException(status_code=400, detail="Missing coordinate values.")

    try:
        res = ctrl.gestures.tap(round(tx, 1), round(ty, 1))
        return {"success": True, "tap_at": {"x": tx, "y": ty}, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SwipeRequest(BaseModel):
    from_x: Optional[float] = None
    from_y: Optional[float] = None
    to_x: Optional[float] = None
    to_y: Optional[float] = None
    norm_from_x: Optional[float] = None
    norm_from_y: Optional[float] = None
    norm_to_x: Optional[float] = None
    norm_to_y: Optional[float] = None
    duration: float = 0.4


@app.post("/api/action/swipe")
def action_swipe(req: SwipeRequest):
    ctrl = get_controller()
    fx, fy = req.from_x, req.from_y
    tx, ty = req.to_x, req.to_y

    if req.norm_from_x is not None and req.norm_from_y is not None:
        try:
            width, height = ctrl.session.get_window_size()
        except Exception:
            width, height = 390, 844
        fx = req.norm_from_x * width
        fy = req.norm_from_y * height
        tx = (req.norm_to_x or req.norm_from_x) * width
        ty = (req.norm_to_y or req.norm_from_y) * height

    try:
        res = ctrl.gestures.swipe(round(fx, 1), round(fy, 1), round(tx, 1), round(ty, 1), req.duration)
        return {"success": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class TextRequest(BaseModel):
    text: str


@app.post("/api/action/type")
def action_type(req: TextRequest):
    ctrl = get_controller()
    try:
        res = ctrl.gestures.send_keys(req.text)
        return {"success": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/action/home")
def action_home():
    ctrl = get_controller()
    try:
        res = ctrl.gestures.press_home()
        return {"success": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/action/lock")
def action_lock():
    ctrl = get_controller()
    try:
        res = ctrl.gestures.lock()
        return {"success": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/action/unlock")
def action_unlock():
    ctrl = get_controller()
    try:
        res = ctrl.gestures.unlock()
        return {"success": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AppLaunchRequest(BaseModel):
    bundle_id: str


@app.post("/api/action/app/launch")
def action_app_launch(req: AppLaunchRequest):
    ctrl = get_controller()
    try:
        res = ctrl.gestures.launch_app(req.bundle_id)
        return {"success": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------
# Logs & Diagnostics
# -------------------------------------------------------------
@app.get("/api/logs")
def get_logs():
    return {"logs": log_records}
