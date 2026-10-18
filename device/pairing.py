import logging
import shutil
import subprocess
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class DevicePairing:
    def __init__(self, go_ios_bin: str = "ios", udid: Optional[str] = None):
        self.go_ios_bin = go_ios_bin
        self.udid = udid

    def check_and_pair(self) -> Tuple[bool, str]:
        """
        Check pairing status and trigger pairing dialog if required.
        Returns: (is_paired, message)
        """
        tool_path = shutil.which(self.go_ios_bin)
        
        # 1. Try go-ios pair
        if tool_path:
            cmd = [tool_path, "pair"]
            if self.udid:
                cmd.extend(["--udid", self.udid])
            
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                output = (res.stdout + " " + res.stderr).strip()
                if res.returncode == 0:
                    return True, "Device successfully paired."
                
                if "Trust This Computer" in output or "locked" in output.lower():
                    return False, "Device is locked or requires 'Trust This Computer' prompt confirmation on iPhone screen."
                
                return False, f"Pairing failed: {output}"
            except subprocess.TimeoutExpired:
                return False, "Pairing timed out. Please check if device screen is unlocked."
            except Exception as e:
                logger.error(f"Error running go-ios pair: {e}")

        # 2. Fallback to pymobiledevice3 usbmux pair
        try:
            cmd = ["python", "-m", "pymobiledevice3", "usbmux", "pair"]
            if self.udid:
                cmd.extend(["--udid", self.udid])
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                return True, "Device successfully paired via pymobiledevice3."
            return False, f"Pairing failed: {res.stderr.strip() or res.stdout.strip()}"
        except Exception as e:
            return False, f"No pairing tool available or execution failed: {e}"
