import json
import logging
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
        return shutil.which(self.go_ios_bin)

    def list_devices(self) -> List[DeviceInfo]:
        """Discover connected devices using go-ios or pymobiledevice3."""
        devices: List[DeviceInfo] = []
        
        # 1. Try go-ios
        tool_path = self._resolve_tool_path()
        if tool_path:
            try:
                # `ios list --details` produces json output
                res = subprocess.run(
                    [tool_path, "list", "--details"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if res.returncode == 0 and res.stdout.strip():
                    try:
                        data = json.loads(res.stdout)
                        # go-ios json format: list of device dicts
                        device_list = data if isinstance(data, list) else data.get("deviceList", [])
                        for item in device_list:
                            devices.append(
                                DeviceInfo(
                                    udid=item.get("Udid", item.get("udid", "")),
                                    device_name=item.get("DeviceName", item.get("deviceName", "Unknown iPhone")),
                                    product_type=item.get("ProductType", item.get("productType", "")),
                                    product_version=item.get("ProductVersion", item.get("productVersion", "Unknown")),
                                    connection_type=item.get("ConnectionType", "USB"),
                                )
                            )
                        if devices:
                            return devices
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse go-ios json output, falling back to text parsing.")
                        # Fallback simple line parsing for `ios list`
                        for line in res.stdout.splitlines():
                            line = line.strip()
                            if line and not line.startswith("UDID"):
                                parts = line.split()
                                if parts:
                                    devices.append(
                                        DeviceInfo(
                                            udid=parts[0],
                                            device_name="iPhone",
                                            product_type="Unknown",
                                            product_version="17.0",  # safe assumption for modern
                                        )
                                    )
                        if devices:
                            return devices
            except Exception as e:
                logger.error(f"Error querying go-ios devices: {e}")

        # 2. Try pymobiledevice3 fallback
        try:
            res = subprocess.run(
                ["python", "-m", "pymobiledevice3", "usbmux", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                for item in data:
                    udid = item.get("SerialNumber", item.get("UniqueDeviceID", ""))
                    if udid:
                        devices.append(
                            DeviceInfo(
                                udid=udid,
                                device_name=item.get("DeviceName", "iPhone"),
                                product_type=item.get("ProductType", "Unknown"),
                                product_version=item.get("ProductVersion", "17.0"),
                                connection_type=item.get("ConnectionType", "USB"),
                            )
                        )
                if devices:
                    return devices
        except Exception:
            pass

        return devices

    def get_default_device(self, preferred_udid: Optional[str] = None) -> Optional[DeviceInfo]:
        """Get the specified device or the first available connected device."""
        devices = self.list_devices()
        if not devices:
            return None
        
        if preferred_udid:
            for d in devices:
                if d.udid.lower() == preferred_udid.lower():
                    return d
            logger.warning(f"Preferred device {preferred_udid} not found in connected devices.")
        
        return devices[0]
