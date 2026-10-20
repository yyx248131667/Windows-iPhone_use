"""USB WDA video, independent of the command channel and bounded to one frame."""
import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

import requests
from airplay.receiver import JPEGParser


class USBScreen:
    def __init__(self, config=None):
        self.config = config or {}
        self.port = int(self.config.get("local_port", 19100))
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._process = None
        self._reader = None
        self._frame = None
        self._sequence = 0
        self._last_frame = 0
        self._lease = 0
        self._error = ""
        self._udid = None

    def start(self, tool, udid):
        with self._lock:
            self._lease = time.monotonic() + 8
            if self._process and self._process.poll() is None and self._udid == udid:
                return
            self.stop()
            executable = str(Path("ios.exe").resolve()) if Path("ios.exe").is_file() else shutil.which(tool)
            if not executable or not udid:
                raise RuntimeError("USB 画面需要已连接的 iPhone 和 go-ios")
            self._stop.clear()
            self._lease = time.monotonic() + 8
            self._udid = udid
            self._error = ""
            self._process = subprocess.Popen(
                [executable, "forward", str(self.port), str(int(self.config.get("device_port", 9100))), "--udid", udid],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            self._reader = threading.Thread(target=self._read, daemon=True)
            self._reader.start()

    def _read(self):
        with requests.Session() as http:
            http.trust_env = False
            while not self._stop.is_set():
                if time.monotonic() > self._lease:
                    self._stop.wait(.2)
                    continue
                try:
                    with http.get(f"http://127.0.0.1:{self.port}", stream=True, timeout=(1, 3)) as response:
                        response.raise_for_status()
                        parser = JPEGParser()
                        for chunk in response.iter_content(4096):
                            if self._stop.is_set() or time.monotonic() > self._lease:
                                break
                            for frame in parser.feed(chunk):
                                self._frame = frame
                                self._sequence += 1
                                self._last_frame = time.monotonic()
                                self._error = ""
                except requests.RequestException:
                    self._error = "USB 连续画面暂不可用，自动模式将使用其他画面来源"
                    self._stop.wait(.5)

    def status(self):
        running = self._process is not None and self._process.poll() is None
        return {"running": running, "streaming": running and self._frame is not None and time.monotonic() - self._last_frame < 3,
                "frames": self._sequence, "error": self._error}

    async def frames(self):
        sequence = -1
        while not self._stop.is_set() and self._process and self._process.poll() is None:
            self._lease = time.monotonic() + 8
            current = self._sequence
            frame = self._frame
            if frame is None or current == sequence:
                await asyncio.sleep(.015)
                continue
            sequence = current
            yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame)).encode()
                   + b"\r\n\r\n" + frame + b"\r\n")

    def stop(self):
        with self._lock:
            self._stop.set()
            if self._process and self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
            if self._reader:
                self._reader.join(timeout=4)
            self._reader = self._process = self._frame = None
            self._last_frame = self._lease = 0
