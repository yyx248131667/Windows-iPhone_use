import io
import logging
from typing import Any, Dict, Optional
import yaml
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
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
from device.discovery import DeviceDiscovery

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Windows-iPhone_use API",
    description="FastAPI service for controlling iPhone via WebDriverAgent on Windows",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global controller instance
controller: Optional[iPhoneController] = None


def get_controller() -> iPhoneController:
    global controller
    if controller is None:
        cfg = {}
        try:
            with open("config/settings.yaml", "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to load config/settings.yaml: {e}")
        controller = iPhoneController(config=cfg)
    return controller


@app.get("/")
def index():
    return {
        "name": "Windows-iPhone_use API",
        "status": "online",
        "docs_url": "/docs",
    }


@app.get("/health")
def health():
    ctrl = get_controller()
    wda_ok = ctrl.client.is_ready()
    return {
        "status": "ok",
        "wda_online": wda_ok,
        "device_udid": ctrl.udid,
    }


@app.get("/device/discovery")
def list_devices():
    ctrl = get_controller()
    devices = ctrl.discovery.list_devices()
    return {"devices": [d.to_dict() for d in devices]}


@app.post("/device/initialize")
def initialize_pipeline(auto_start_tunnel: bool = True, auto_start_wda: bool = True):
    ctrl = get_controller()
    ok, msg = ctrl.initialize(auto_start_tunnel=auto_start_tunnel, auto_start_wda=auto_start_wda)
    if not ok:
        raise HTTPException(status_code=500, detail=msg)
    return {"success": True, "message": msg}


@app.get("/wda/status")
def wda_status():
    ctrl = get_controller()
    try:
        return ctrl.client.status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"WDA status error: {e}")


@app.get("/screenshot")
def get_screenshot(raw: bool = Query(default=False, description="Return raw PNG image bytes instead of JSON")):
    ctrl = get_controller()
    try:
        if raw:
            png_bytes = ctrl.screenshot.get_bytes()
            return Response(content=png_bytes, media_type="image/png")
        else:
            b64_str = ctrl.capture_screenshot_base64()
            return {"format": "png", "base64": b64_str}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to capture screenshot: {e}")


@app.get("/source")
def get_ui_hierarchy(format_type: str = "xml"):
    ctrl = get_controller()
    try:
        source = ctrl.elements.get_source(format_type=format_type)
        return {"source": source}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch UI hierarchy: {e}")


class GenericActionRequest(BaseModel):
    action: Dict[str, Any]


@app.post("/action/execute")
def execute_action(req: GenericActionRequest):
    ctrl = get_controller()
    try:
        action_obj = parse_action(req.action)
        result = ctrl.execute_action(action_obj)
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/action/tap")
def action_tap(x: float, y: float):
    ctrl = get_controller()
    try:
        res = ctrl.execute_action(TapAction(x=x, y=y))
        return {"success": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/action/swipe")
def action_swipe(from_x: float, from_y: float, to_x: float, to_y: float, duration: float = 0.5):
    ctrl = get_controller()
    try:
        res = ctrl.execute_action(SwipeAction(from_x=from_x, from_y=from_y, to_x=to_x, to_y=to_y, duration=duration))
        return {"success": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/action/type")
def action_type(text: str):
    ctrl = get_controller()
    try:
        res = ctrl.execute_action(InputAction(text=text))
        return {"success": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/action/home")
def action_home():
    ctrl = get_controller()
    try:
        res = ctrl.gestures.press_home()
        return {"success": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/action/app/launch")
def action_launch_app(bundle_id: str):
    ctrl = get_controller()
    try:
        res = ctrl.execute_action(LaunchAppAction(bundle_id=bundle_id))
        return {"success": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/action/app/terminate")
def action_terminate_app(bundle_id: str):
    ctrl = get_controller()
    try:
        res = ctrl.execute_action(TerminateAppAction(bundle_id=bundle_id))
        return {"success": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/device/shutdown")
def shutdown():
    ctrl = get_controller()
    ctrl.shutdown()
    return {"success": True, "message": "Controller shutdown completed."}
