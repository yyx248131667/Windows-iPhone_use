import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Optional, Tuple
import requests

logger = logging.getLogger(__name__)


class WDARunner:
    """
    Drives the XCTest execution mechanism to start WebDriverAgent on the target iOS device.
    Verifies that the runner is properly booted and WDA HTTP server is listening.
    """

    def __init__(
        self,
        go_ios_bin: str = "ios",
        udid: Optional[str] = None,
        bundle_id: str = "com.facebook.WebDriverAgentRunner.xctrunner",
        testrunner_bundle_id: str = "com.facebook.WebDriverAgentRunner.xctrunner",
        xctestrun_path: Optional[str] = None,
        wda_base_url: str = "http://127.0.0.1:8100",
    ):
        self.go_ios_bin = go_ios_bin
        self.udid = udid
        self.bundle_id = bundle_id
        self.testrunner_bundle_id = testrunner_bundle_id
        self.xctestrun_path = xctestrun_path
        self.wda_base_url = wda_base_url.rstrip("/")
        self._process: Optional[subprocess.Popen] = None
        self._log_thread: Optional[threading.Thread] = None
        self._last_logs = []

    def _get_help_text(self, tool_path: str, command: str) -> str:
        """Fetch help text for a sub-command to verify supported arguments."""
        try:
            res = subprocess.run([tool_path, command, "--help"], capture_output=True, text=True, timeout=5)
            return (res.stdout + " " + res.stderr).lower()
        except Exception:
            return ""

    def build_command(self) -> Tuple[list, str]:
        """Construct the appropriate XCTest execution command based on installed tool."""
        tool_path = shutil.which(self.go_ios_bin)
        if not tool_path:
            return [], "go-ios executable not found in PATH."

        # Check whether `runwda` or `runtest` is available
        main_help = self._get_help_text(tool_path, "")
        
        cmd = [tool_path]
        if "runwda" in main_help:
            cmd.append("runwda")
            sub_help = self._get_help_text(tool_path, "runwda")
        elif "runtest" in main_help:
            cmd.append("runtest")
            sub_help = self._get_help_text(tool_path, "runtest")
        else:
            # Fallback to runwda default
            cmd.append("runwda")
            sub_help = ""

        if self.udid:
            cmd.extend(["--udid", self.udid])

        if "--bundleid" in sub_help or not sub_help:
            cmd.extend(["--bundleid", self.bundle_id])
        
        if "--testrunnerbundleid" in sub_help:
            cmd.extend(["--testrunnerbundleid", self.testrunner_bundle_id])

        if self.xctestrun_path and os.path.exists(self.xctestrun_path):
            if "--xctestrunpath" in sub_help or not sub_help:
                cmd.extend(["--xctestrunpath", os.path.abspath(self.xctestrun_path)])

        return cmd, "Command built successfully."

    def start(self, timeout_seconds: int = 40) -> Tuple[bool, str]:
        """
        Start the WDA test runner process and wait until the HTTP server is responsive.
        """
        if self._process and self._process.poll() is None:
            if self.wait_for_ready(timeout_seconds=5):
                return True, "WDA is already running and responsive."

        cmd, msg = self.build_command()
        if not cmd:
            return False, f"Failed to build WDA runner command: {msg}"

        logger.info(f"Starting WDA runner: {' '.join(cmd)}")
        self._last_logs = []

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )

            def _read_output(proc):
                for line in iter(proc.stdout.readline, ""):
                    line_str = line.strip()
                    if line_str:
                        logger.info(f"[WDA STDOUT] {line_str}")
                        self._last_logs.append(line_str)
                for line in iter(proc.stderr.readline, ""):
                    line_str = line.strip()
                    if line_str:
                        logger.warning(f"[WDA STDERR] {line_str}")
                        self._last_logs.append(f"[ERR] {line_str}")

            self._log_thread = threading.Thread(target=_read_output, args=(self._process,), daemon=True)
            self._log_thread.start()

            # Poll WDA /status endpoint
            logger.info(f"Waiting up to {timeout_seconds}s for WDA server at {self.wda_base_url}/status ...")
            if self.wait_for_ready(timeout_seconds=timeout_seconds):
                return True, "WDA server is running and verified responsive."
            else:
                # Check if process died
                if self._process.poll() is not None:
                    recent = "\n".join(self._last_logs[-10:])
                    return False, f"WDA process exited prematurely (code {self._process.returncode}). Logs:\n{recent}"
                return False, f"Timed out waiting for WDA HTTP server at {self.wda_base_url}/status."

        except Exception as e:
            return False, f"Failed to launch WDA runner: {e}"

    def wait_for_ready(self, timeout_seconds: int = 30) -> bool:
        """Poll /status endpoint until it responds with HTTP 200."""
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                resp = requests.get(f"{self.wda_base_url}/status", timeout=2.0)
                if resp.status_code == 200:
                    logger.info("WDA server healthcheck responded with HTTP 200 OK.")
                    return True
            except requests.RequestException:
                pass

            # Check if process terminated early
            if self._process and self._process.poll() is not None:
                logger.error(f"WDA process exited during wait (code {self._process.returncode}).")
                return False

            time.sleep(1.0)
        return False

    def stop(self) -> None:
        """Stop WDA test runner."""
        if self._process and self._process.poll() is None:
            logger.info(f"Terminating WDA runner process (PID: {self._process.pid})...")
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                self._process.kill()
            finally:
                self._process = None

    def is_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None
