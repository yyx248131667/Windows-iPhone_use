import logging
import os
import shutil
import subprocess
import zipfile
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class AppInstaller:
    """
    Handles installation and validation of WebDriverAgentRunner IPA or .app bundle.
    """

    def __init__(self, go_ios_bin: str = "ios", udid: Optional[str] = None):
        self.go_ios_bin = go_ios_bin
        self.udid = udid

    def verify_ipa_structure(self, file_path: str) -> Tuple[bool, str]:
        """
        Verify that an IPA file contains the expected WebDriverAgentRunner payload structure.
        """
        if not os.path.exists(file_path):
            return False, f"File does not exist: {file_path}"

        if file_path.endswith(".ipa") or file_path.endswith(".zip"):
            try:
                with zipfile.ZipFile(file_path, "r") as zf:
                    namelist = zf.namelist()
                    has_runner = any("WebDriverAgentRunner" in name for name in namelist)
                    has_info_plist = any("Info.plist" in name for name in namelist)
                    if not (has_runner and has_info_plist):
                        return False, "Archive does not appear to contain a valid WebDriverAgentRunner app payload."
                return True, "IPA structure verified."
            except Exception as e:
                return False, f"Corrupted or invalid archive file: {e}"
        elif os.path.isdir(file_path):
            info_plist = os.path.join(file_path, "Info.plist")
            if not os.path.exists(info_plist):
                return False, f"Missing Info.plist in directory: {file_path}"
            return True, "App bundle directory verified."

        return True, "File format accepted."

    def install(self, package_path: str) -> Tuple[bool, str]:
        """
        Install an IPA or .app bundle to the target iOS device.
        """
        valid, msg = self.verify_ipa_structure(package_path)
        if not valid:
            return False, f"Package validation failed: {msg}"

        tool_path = None
        for candidate in ["ios.exe", "ios", os.path.join(os.path.dirname(__file__), "..", "ios.exe")]:
            if os.path.exists(candidate):
                tool_path = os.path.abspath(candidate)
                break
        if not tool_path:
            tool_path = shutil.which(self.go_ios_bin)

        # 1. Try go-ios install
        if tool_path:
            cmd = [tool_path, "install", "--path", package_path]
            if self.udid:
                cmd.extend(["--udid", self.udid])
            
            try:
                logger.info(f"Installing package with go-ios: {' '.join(cmd)}")
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if res.returncode == 0:
                    return True, "Application installed successfully via go-ios."
                return False, f"go-ios install failed: {res.stderr.strip() or res.stdout.strip()}"
            except subprocess.TimeoutExpired:
                return False, "Installation timed out after 120 seconds."
            except Exception as e:
                logger.error(f"Error during go-ios installation: {e}")

        # 2. Fallback to pymobiledevice3 apps install
        try:
            cmd = ["python", "-m", "pymobiledevice3", "apps", "install", package_path]
            if self.udid:
                cmd.extend(["--udid", self.udid])
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if res.returncode == 0:
                return True, "Application installed successfully via pymobiledevice3."
            return False, f"pymobiledevice3 install failed: {res.stderr.strip() or res.stdout.strip()}"
        except Exception as e:
            return False, f"No installation tool available: {e}"

    def list_installed_apps(self) -> Tuple[bool, list]:
        """List bundle IDs of installed applications."""
        tool_path = shutil.which(self.go_ios_bin)
        if tool_path:
            cmd = [tool_path, "apps"]
            if self.udid:
                cmd.extend(["--udid", self.udid])
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if res.returncode == 0:
                    lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                    return True, lines
            except Exception as e:
                logger.warning(f"Failed to list apps via go-ios: {e}")

        return False, []
