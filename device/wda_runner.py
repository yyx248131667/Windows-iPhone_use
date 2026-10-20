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
        self._diagnostic_process: Optional[subprocess.Popen] = None
        self._last_logs = []

    def _get_help_text(self, tool_path: str, command: str) -> str:
        """Fetch help text for a sub-command to verify supported arguments."""
        try:
            res = subprocess.run([tool_path, command, "--help"], capture_output=True, text=True, timeout=5)
            return (res.stdout + " " + res.stderr).lower()
        except Exception:
            return ""

    def _resolve_xctestrun(self) -> Optional[str]:
        """Find .xctestrun file if path not explicitly set or not found."""
        if self.xctestrun_path and os.path.exists(self.xctestrun_path):
            return self.xctestrun_path
        
        # Search candidate locations
        search_dirs = ["artifacts", "WDA-Full-XCTest-Bundle", "."]
        for d in search_dirs:
            if os.path.exists(d):
                for root, _, files in os.walk(d):
                    for f in files:
                        if f.endswith(".xctestrun"):
                            return os.path.join(root, f)
        return None

    def build_command(self) -> Tuple[list, str]:
        """Construct the appropriate XCTest execution command based on installed tool."""
        tool_path = None
        for candidate in ["ios.exe", "ios", os.path.join(os.path.dirname(__file__), "..", "ios.exe")]:
            if os.path.exists(candidate):
                tool_path = os.path.abspath(candidate)
                break
        if not tool_path:
            tool_path = shutil.which(self.go_ios_bin)
        if not tool_path:
            return [], "go-ios executable not found in PATH or workspace."

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

        # go-ios requires: either NONE of bundleid, testrunnerbundleid and xctestconfig or ALL of them.
        is_default_bundle = (
            self.bundle_id == "com.facebook.WebDriverAgentRunner.xctrunner"
            and self.testrunner_bundle_id == "com.facebook.WebDriverAgentRunner.xctrunner"
        )
        if not is_default_bundle:
            cmd.extend(["--bundleid", self.bundle_id])
            cmd.extend(["--testrunnerbundleid", self.testrunner_bundle_id])
            cmd.extend(["--xctestconfig", "WebDriverAgentRunner.xctest"])

        # Local tunnel APIs must bypass the workstation's outbound proxy.
        with requests.Session() as http:
            http.trust_env = False
            for port in (60105, 28100):
                try:
                    response = http.get(f"http://127.0.0.1:{port}/tunnels", timeout=2)
                    response.raise_for_status()
                    infos = response.json()
                    if not isinstance(infos, list):
                        continue
                    info = next((t for t in infos if not self.udid or t.get("udid") == self.udid), None)
                    if not info or not info.get("address") or not info.get("rsdPort"):
                        continue
                    cmd.extend(["--address", info["address"], "--rsd-port", str(info["rsdPort"])])
                    if info.get("userspaceTun"):
                        cmd.extend(["--userspace-port", str(info["userspaceTunPort"])])
                    break
                except (requests.RequestException, ValueError, KeyError, TypeError):
                    continue
        return cmd, "Command built successfully."

    def start(self, timeout_seconds: int = 40) -> Tuple[bool, str]:
        """
        Start the WDA test runner process and wait until the HTTP server is responsive.
        """
        if self._process and self._process.poll() is None:
            if self.wait_for_ready(timeout_seconds=5):
                return True, "WDA is already running and responsive."

        self.stop()
        cmd, msg = self.build_command()
        if not cmd:
            return False, f"Failed to build WDA runner command: {msg}"

        logger.info(f"Starting WDA runner: {' '.join(cmd)}")
        self._last_logs = []

        try:
            # Capture device-side XCTest failures which runwda may never report.
            diagnostic_cmd = [cmd[0], "ostrace", "--match=Failed to establish connection to the IDE"]
            if self.udid:
                diagnostic_cmd.extend(["--udid", self.udid])
            for flag in ("--address", "--rsd-port", "--userspace-port"):
                if flag in cmd:
                    diagnostic_cmd.extend([flag, cmd[cmd.index(flag) + 1]])
            self._diagnostic_process = subprocess.Popen(
                diagnostic_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )

            def _read_diagnostics(proc):
                for line in proc.stdout:
                    if "Failed to establish connection to the IDE" in line:
                        detail = "手机端 WDA 无法建立 XCTest IDE 连接并退出；请检查 WDA 包与设备系统、XCTest 驱动的兼容性。"
                        logger.error(detail)
                        self._last_logs.append(detail)
                        self._last_logs.append(line.strip())

            threading.Thread(target=_read_diagnostics, args=(self._diagnostic_process,), daemon=True).start()
            time.sleep(1.0)
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8", errors="replace",
                bufsize=1,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )

            def _read_output(proc):
                for line in iter(proc.stdout.readline, ""):
                    line_str = line.strip()
                    if line_str:
                        logger.info(f"[WDA STDOUT] {line_str}")
                        self._last_logs.append(line_str)

            self._log_thread = threading.Thread(target=_read_output, args=(self._process,), daemon=True)
            self._log_thread.start()

            # Poll WDA /status endpoint
            logger.info(f"Waiting up to {timeout_seconds}s for WDA server at {self.wda_base_url}/status ...")
            if self.wait_for_ready(timeout_seconds=timeout_seconds):
                self._stop_diagnostics()
                return True, "WDA server is running and verified responsive."
            else:
                # Check if process died
                if self._process.poll() is not None:
                    if self._log_thread:
                        self._log_thread.join(timeout=1)
                    recent = "\n".join(self._last_logs[-10:])
                    self._stop_diagnostics()
                    return False, f"WDA process exited prematurely (code {self._process.returncode}). Logs:\n{recent}"
                recent = "\n".join(self._last_logs[-10:])
                self.stop()
                if "Failed to establish connection to the IDE" in recent:
                    return False, f"手机端 WDA 在 XCTest 握手阶段退出。日志:\n{recent}"
                return False, f"Timed out waiting for WDA HTTP server at {self.wda_base_url}/status. Logs:\n{recent}"

        except Exception as e:
            self.stop()
            return False, f"Failed to launch WDA runner: {e}"

    def wait_for_ready(self, timeout_seconds: int = 30) -> bool:
        """Poll /status endpoint until it responds with HTTP 200."""
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if any("Failed to establish connection to the IDE" in line for line in self._last_logs):
                return False
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

    def _stop_diagnostics(self) -> None:
        proc = self._diagnostic_process
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        self._diagnostic_process = None

    def stop(self) -> None:
        """Stop WDA test runner."""
        self._stop_diagnostics()
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
