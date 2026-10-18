import logging
import os
import shutil
import socket
import subprocess
import threading
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class TunnelManager:
    """
    Manages communication tunnels and port forwards for iOS devices on Windows.
    - iOS 17+: Starts `ios tunnel start` or `pymobiledevice3 remote tunneld` (CoreDevice/RemoteXPC).
    - iOS < 17: Sets up direct port forwarding via `ios forward` or `iproxy`.
    """

    def __init__(
        self,
        go_ios_bin: str = "ios",
        udid: Optional[str] = None,
        local_port: int = 8100,
        device_port: int = 8100,
        ios_version: Optional[str] = None,
    ):
        self.go_ios_bin = go_ios_bin
        self.udid = udid
        self.local_port = local_port
        self.device_port = device_port
        self.ios_version = ios_version
        self._process: Optional[subprocess.Popen] = None
        self._is_running = False
        self._log_thread: Optional[threading.Thread] = None

    @property
    def is_ios_17_plus(self) -> bool:
        if not self.ios_version:
            return True  # Default to iOS 17+ tunnel mode for modern devices
        try:
            major = int(self.ios_version.split(".")[0])
            return major >= 17
        except Exception:
            return True

    def is_port_listening(self, host: str = "127.0.0.1", port: Optional[int] = None) -> bool:
        """Check if local port is open and listening."""
        port = port or self.local_port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            result = s.connect_ex((host, port))
            return result == 0

    def start_tunnel(self) -> Tuple[bool, str]:
        """Start the tunnel or port-forwarding process in background."""
        if self._process and self._process.poll() is None:
            return True, "Tunnel process is already running."

        tool_path = shutil.which(self.go_ios_bin)
        
        # Decide command based on iOS version
        if self.is_ios_17_plus:
            logger.info("iOS 17+ detected: Starting CoreDevice tunnel...")
            if tool_path:
                cmd = [tool_path, "tunnel", "start"]
                if self.udid:
                    cmd.extend(["--udid", self.udid])
            else:
                # Fallback to pymobiledevice3 remote tunneld
                cmd = ["python", "-m", "pymobiledevice3", "remote", "tunneld"]
                if self.udid:
                    cmd.extend(["--udid", self.udid])
        else:
            logger.info("iOS < 17 detected: Starting direct port forward...")
            if tool_path:
                cmd = [tool_path, "forward", str(self.local_port), str(self.device_port)]
                if self.udid:
                    cmd.extend(["--udid", self.udid])
            else:
                cmd = ["iproxy", str(self.local_port), str(self.device_port)]

        try:
            logger.info(f"Executing tunnel command: {' '.join(cmd)}")
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            self._is_running = True

            # Start background logger
            def _log_output(proc: subprocess.Popen):
                for line in iter(proc.stdout.readline, ""):
                    if line:
                        logger.debug(f"[Tunnel STDOUT] {line.strip()}")
                for line in iter(proc.stderr.readline, ""):
                    if line:
                        logger.warning(f"[Tunnel STDERR] {line.strip()}")

            self._log_thread = threading.Thread(target=_log_output, args=(self._process,), daemon=True)
            self._log_thread.start()

            # Wait briefly to ensure it didn't exit immediately with an error
            time.sleep(1.5)
            if self._process.poll() is not None:
                err = self._process.stderr.read() if self._process.stderr else "Unknown error"
                self._is_running = False
                return False, f"Tunnel process exited immediately (code {self._process.returncode}): {err.strip()}"

            return True, f"Tunnel started successfully (PID: {self._process.pid})."

        except FileNotFoundError:
            return False, f"Tunnel tool '{cmd[0]}' not found in PATH. Please install go-ios or pymobiledevice3."
        except Exception as e:
            return False, f"Failed to start tunnel: {e}"

    def stop_tunnel(self) -> None:
        """Gracefully stop the background tunnel process."""
        if self._process and self._process.poll() is None:
            logger.info(f"Terminating tunnel process (PID: {self._process.pid})...")
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                self._process.kill()
            finally:
                self._process = None
                self._is_running = False

    def is_alive(self) -> bool:
        """Check if tunnel process is alive and active."""
        if self._process and self._process.poll() is None:
            return True
        return False
