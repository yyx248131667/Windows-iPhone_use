import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DeviceInfo:
    udid: str
    device_name: str
    product_type: str
    product_version: str  # e.g. "17.4.1"
    connection_type: str = "USB"  # USB or Network

    @property
    def is_ios_17_plus(self) -> bool:
        """Check if iOS version is 17.0 or higher (requiring CoreDevice tunnel)."""
        try:
            major = int(self.product_version.split(".")[0])
            return major >= 17
        except Exception:
            return False

    def to_dict(self) -> dict:
        return {
            "udid": self.udid,
            "device_name": self.device_name,
            "product_type": self.product_type,
            "product_version": self.product_version,
            "connection_type": self.connection_type,
            "is_ios_17_plus": self.is_ios_17_plus,
        }


class DeviceDiscovery:
    def __init__(self, go_ios_bin: str = "ios"):
        self.go_ios_bin = go_ios_bin

    def _resolve_tool_path(self) -> Optional[str]:
        """Find executable path for go-ios or fallback."""
        for candidate in ["ios.exe", "ios", os.path.join(os.path.dirname(__file__), "..", "ios.exe")]:
            if os.path.exists(candidate):
                return os.path.abspath(candidate)
        return shutil.which(self.go_ios_bin)

    def list_devices(self) -> List[DeviceInfo]:
        """Discover connected devices using go-ios or pymobiledevice3."""
        devices: List[DeviceInfo] = []
        
        # 1. Try fast `ios list` first, then `--details`
        tool_path = self._resolve_tool_path()
        if tool_path:
            try:
                for cmd_args in [["list", "--details"], ["list"]]:
                    res = subprocess.run([tool_path] + cmd_args, capture_output=True, text=True, timeout=4)
                    if res.returncode == 0 and res.stdout.strip():
                        for line in res.stdout.splitlines():
                            line = line.strip()
                            if not line or not line.startswith("{"):
                                continue
                            try:
                                obj = json.loads(line)
                                if isinstance(obj, dict) and "deviceList" in obj:
                                    for item in obj["deviceList"]:
                                        if isinstance(item, dict):
                                            udid = item.get("Udid") or item.get("udid") or ""
                                            ptype = item.get("ProductType") or item.get("productType") or ""
                                            pver = str(item.get("ProductVersion") or item.get("productVersion") or "17.0")
                                            dname = item.get("DeviceName") or item.get("deviceName") or "iPhone"
                                            if udid:
                                                devices.append(DeviceInfo(
                                                    udid=udid,
                                                    device_name=dname,
                                                    product_type=ptype,
                                                    product_version=pver,
                                                    connection_type=item.get("ConnectionType", "USB"),
                                                ))
                                        elif isinstance(item, str) and len(item) > 10:
                                            devices.append(DeviceInfo(
                                                udid=item,
                                                device_name="iPhone",
                                                product_type="iPhone",
                                                product_version="17.0",
                                                connection_type="USB",
                                            ))
                            except json.JSONDecodeError:
                                pass
                    if devices:
                        return devices
            except Exception as e:
                logger.warning(f"go-ios list check: {e}")

        return devices

    def get_default_device(self, preferred_udid: Optional[str] = None) -> Optional[DeviceInfo]:
        """Get the specified device or the first available connected device."""
        devices = self.list_devices()
        if devices:
            if preferred_udid:
                clean_pref = preferred_udid.replace("-", "").lower()
                for d in devices:
                    clean_d = d.udid.replace("-", "").lower()
                    if clean_d == clean_pref:
                        return d
            return devices[0]

        return None
