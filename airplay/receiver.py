"""UxPlay process and a loopback-only GStreamer JPEG bridge.

The phone sends AirPlay video; WDA remains the independent control channel.
Only the latest decoded frame is retained, so slow viewers cannot build a queue.
"""
import asyncio
import logging
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time

logger = logging.getLogger(__name__)


class JPEGParser:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, chunk):
        self.buffer.extend(chunk)
        frames = []
        while True:
            start = self.buffer.find(b"\xff\xd8")
            if start < 0:
                self.buffer[:] = self.buffer[-1:]
                break
            if start:
                del self.buffer[:start]
            end = self.buffer.find(b"\xff\xd9", 2)
            if end < 0:
                if len(self.buffer) > 16 * 1024 * 1024:
                    self.buffer.clear()
                break
            frames.append(bytes(self.buffer[:end + 2]))
            del self.buffer[:end + 2]
        return frames


class AirPlayReceiver:
    def __init__(self, config=None):
        self.config = config or {}
        self.name = self.config.get("name", "Windows-iPhone")
        self.port = int(self.config.get("bridge_port", 7110))
        self._process = None
        self._stop = threading.Event()
        self._condition = threading.Condition()
        self._lifecycle = threading.RLock()
        self._socket = None
        self._frame = None
        self._sequence = 0
        self._last_frame = 0.0
        self._logs = []
        self._reader = None

    def executable(self):
        configured = self.config.get("uxplay_bin")
        candidates = [configured] if configured else []
        candidates += [
            ".runtime/airplay/msys64/ucrt64/bin/uxplay.exe",
            "tools/uxplay/uxplay.exe",
            shutil.which("uxplay"),
        ]
        return next((str(Path(p).resolve()) for p in candidates if p and Path(p).is_file()), None)

    def build_command(self, executable):
        # A sink bin can be supplied to UxPlay -vs. The TCP endpoint is private
        # to this host; FastAPI exposes frames to its own browser clients.
        sink = ("queue leaky=downstream max-size-buffers=1 max-size-bytes=0 max-size-time=0 ! "
                "videoconvert ! videoscale ! video/x-raw,format=I420 ! "
                "jpegenc quality=75 ! multipartmux boundary=frame ! "
                f"tcpserversink host=127.0.0.1 port={self.port} sync=false buffers-max=8 buffers-soft-max=4 recover-policy=latest")
        return [executable, "-n", self.name, "-s", "720x1280@30", "-fps", "30",
                "-as", "0", "-vsync", "no", "-p", str(int(self.config.get("port", 7100))),
                "-vs", sink]

    def start(self):
        with self._lifecycle:
            if self._process and self._process.poll() is None:
                return self.status()
            if self._process is not None:
                self.stop()
            executable = self.executable()
            if not executable:
                raise RuntimeError("尚未安装 UxPlay 接收器，请参阅 README 的 AirPlay 安装说明。")
            self._stop.clear()
            self._logs.clear()
            self._frame = None
            self._last_frame = 0.0
            env = os.environ.copy()
            env["PATH"] = str(Path(executable).parent) + os.pathsep + env.get("PATH", "")
            state = Path(".runtime/airplay/state").resolve()
            state.mkdir(parents=True, exist_ok=True)
            self._process = subprocess.Popen(
                self.build_command(executable), cwd=state, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            threading.Thread(target=self._read_logs, args=(self._process,), daemon=True).start()
            self._reader = threading.Thread(target=self._read_frames, daemon=True)
            self._reader.start()
            return self.status()

    def _read_logs(self, process):
        for line in process.stdout:
            line = line.strip()
            if line:
                self._logs.append(line)
                del self._logs[:-50]
                logger.info("[AirPlay] %s", line)

    def _read_frames(self):
        while not self._stop.is_set() and self._process and self._process.poll() is None:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=1) as conn:
                    self._socket = conn
                    conn.settimeout(1)
                    parser = JPEGParser()
                    while not self._stop.is_set():
                        try:
                            chunk = conn.recv(65536)
                        except socket.timeout:
                            continue
                        if not chunk:
                            break
                        for frame in parser.feed(chunk):
                            with self._condition:
                                self._frame = frame
                                self._sequence += 1
                                self._last_frame = time.monotonic()
                                self._condition.notify_all()
            except OSError:
                pass
            finally:
                self._socket = None
            self._stop.wait(0.3)

    def status(self):
        running = self._process is not None and self._process.poll() is None
        active = running and self._frame is not None and time.monotonic() - self._last_frame < float(self.config.get("stale_timeout", 10))
        return {"available": self.executable() is not None, "running": running,
                "streaming": active, "name": self.name, "frames": self._sequence,
                "message": "画面已连接" if active else "在 iPhone 控制中心打开屏幕镜像，选择 " + self.name if running else "接收器未启动",
                "logs": self._logs[-5:] if not running else [],
                "error": self._logs[-1] if not running and self._process and self._logs else ""}

    async def frames(self):
        sequence = -1
        while not self._stop.is_set():
            if self._process is None or self._process.poll() is not None:
                break
            with self._condition:
                frame = self._frame if self._sequence != sequence else None
                if frame is not None:
                    sequence = self._sequence
            if frame is None:
                await asyncio.sleep(0.02)
                continue
            yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                   + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")


    def stop(self):
        with self._lifecycle:
            self._stop.set()
            if self._socket:
                try:
                    self._socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            if self._process and self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
            self._process = None
            with self._condition:
                self._condition.notify_all()
            if self._reader:
                self._reader.join(timeout=2)
            self._frame = None
            self._last_frame = 0.0
