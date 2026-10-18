from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    TAP = "tap"
    DOUBLE_TAP = "double_tap"
    LONG_PRESS = "long_press"
    SWIPE = "swipe"
    SCROLL = "scroll"
    INPUT_TEXT = "input_text"
    PRESS_HOME = "press_home"
    LOCK = "lock"
    UNLOCK = "unlock"
    LAUNCH_APP = "launch_app"
    TERMINATE_APP = "terminate_app"
    SCREENSHOT = "screenshot"
    WAIT = "wait"


class BaseAction(BaseModel):
    action_type: ActionType


class TapAction(BaseAction):
    action_type: ActionType = ActionType.TAP
    x: float
    y: float


class DoubleTapAction(BaseAction):
    action_type: ActionType = ActionType.DOUBLE_TAP
    x: float
    y: float


class LongPressAction(BaseAction):
    action_type: ActionType = ActionType.LONG_PRESS
    x: float
    y: float
    duration: float = 1.0


class SwipeAction(BaseAction):
    action_type: ActionType = ActionType.SWIPE
    from_x: float
    from_y: float
    to_x: float
    to_y: float
    duration: float = 0.5


class ScrollAction(BaseAction):
    action_type: ActionType = ActionType.SCROLL
    direction: str = "down"  # up, down, left, right


class InputAction(BaseAction):
    action_type: ActionType = ActionType.INPUT_TEXT
    text: str


class LaunchAppAction(BaseAction):
    action_type: ActionType = ActionType.LAUNCH_APP
    bundle_id: str


class TerminateAppAction(BaseAction):
    action_type: ActionType = ActionType.TERMINATE_APP
    bundle_id: str


class WaitAction(BaseAction):
    action_type: ActionType = ActionType.WAIT
    seconds: float = 1.0


def parse_action(data: Dict[str, Any]) -> BaseAction:
    """Parse dictionary into appropriate typed Action model."""
    atype = data.get("action_type") or data.get("type")
    if not atype:
        raise ValueError("Missing action_type or type field in action payload.")
    
    atype = ActionType(atype)
    action_cls_map = {
        ActionType.TAP: TapAction,
        ActionType.DOUBLE_TAP: DoubleTapAction,
        ActionType.LONG_PRESS: LongPressAction,
        ActionType.SWIPE: SwipeAction,
        ActionType.SCROLL: ScrollAction,
        ActionType.INPUT_TEXT: InputAction,
        ActionType.PRESS_HOME: BaseAction,
        ActionType.LOCK: BaseAction,
        ActionType.UNLOCK: BaseAction,
        ActionType.LAUNCH_APP: LaunchAppAction,
        ActionType.TERMINATE_APP: TerminateAppAction,
        ActionType.SCREENSHOT: BaseAction,
        ActionType.WAIT: WaitAction,
    }
    cls = action_cls_map.get(atype, BaseAction)
    return cls(**data)
