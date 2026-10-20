import asyncio
import io
import socket
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image
from airplay.receiver import AirPlayReceiver, JPEGParser


def jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (48, 96), "blue").save(buf, format="JPEG")
    return buf.getvalue()


class ParserTests(unittest.TestCase):
    def test_fragmented_multipart_and_multiple_frames(self):
        frame = jpeg()
        source = b"--frame\r\nContent-Length: 99\r\n\r\n" + frame + b"\r\n--frame\r\n" + frame
        parser, frames = JPEGParser(), []
        for byte in source:
            frames.extend(parser.feed(bytes([byte])))
        self.assertEqual(frames, [frame, frame])

    def test_incomplete_frame_is_bounded(self):
        parser = JPEGParser()
        parser.feed(b"\xff\xd8" + b"x" * (16 * 1024 * 1024))
        self.assertEqual(parser.buffer, b"")

    def test_receiver_sink_is_loopback_only(self):
        args = AirPlayReceiver().build_command("uxplay")
        self.assertIn("host=127.0.0.1", args[-1])
        self.assertNotIn("0.0.0.0", args[-1])
        self.assertIn("jpegenc", args[-1])

    def test_tcp_reader_receives_frames_and_stops(self):
        frame = jpeg()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            receiver = AirPlayReceiver({"bridge_port": listener.getsockname()[1]})
            receiver._process = MagicMock()
            receiver._process.poll.return_value = None
            receiver._reader = threading.Thread(target=receiver._read_frames, daemon=True)
            receiver._reader.start()
            conn, _ = listener.accept()
            with conn:
                conn.sendall(frame)
                deadline = time.monotonic() + 2
                while receiver._frame is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual(receiver._frame, frame)
                self.assertTrue(receiver.status()["streaming"])
                receiver.stop()
            self.assertFalse(receiver._reader.is_alive())
            self.assertFalse(receiver.status()["streaming"])


class StreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_latest_frame_only_and_stream_is_cancellable(self):
        receiver = AirPlayReceiver()
        receiver._process = MagicMock()
        receiver._process.poll.return_value = None
        receiver._frame, receiver._sequence = b"latest", 10
        stream = receiver.frames()
        chunk = await anext(stream)
        self.assertIn(b"latest", chunk)
        pending = asyncio.create_task(anext(stream))
        await asyncio.sleep(0.03)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        await stream.aclose()
