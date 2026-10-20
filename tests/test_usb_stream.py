import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import unittest
from unittest.mock import Mock, patch

from wda.stream import USBScreen


class USBStreamTests(unittest.TestCase):
    def test_fragmented_http_frames_and_stop(self):
        frame = b"\xff\xd8example\xff\xd9"

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                try:
                    for _ in range(100):
                        self.wfile.write(b"--boundary\r\n\r\n" + frame * 500)
                        self.wfile.flush()
                        time.sleep(.01)
                except OSError:
                    pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        screen = USBScreen({"local_port": server.server_port})
        process = Mock()
        process.poll.return_value = None
        try:
            with patch("wda.stream.subprocess.Popen", return_value=process):
                screen.start("ios", "test-device")
                deadline = time.monotonic() + 2
                while not screen.status()["streaming"] and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(screen.status()["streaming"])
                self.assertEqual(screen._frame, frame)
                reader = screen._reader
                screen.stop()
                self.assertFalse(reader.is_alive())
                self.assertFalse(screen.status()["running"])
                process.terminate.assert_called_once()
        finally:
            screen.stop()
            server.shutdown()
            server.server_close()

    def test_async_stream_cancellation_does_not_block(self):
        async def check():
            screen = USBScreen()
            screen._process = Mock()
            screen._process.poll.return_value = None
            stream = screen.frames()
            task = asyncio.create_task(anext(stream))
            await asyncio.sleep(.03)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            await stream.aclose()
        asyncio.run(check())
