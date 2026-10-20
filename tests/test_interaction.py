import io
import unittest
import requests
from unittest.mock import MagicMock, patch
from PIL import Image
from wda.client import WDAClient, WDAError
from wda.gestures import WDAGestures
from wda.session import WDASession
from api import server
from device.discovery import DeviceDiscovery


class InteractionTests(unittest.TestCase):
    def test_fast_touch_requires_portrait_and_real_completion(self):
        client, session = MagicMock(), MagicMock()
        session.ensure_session.return_value = "sid"
        session._window_size = (430, 932)
        client.post.return_value = {"value": {"completed": True}}
        gestures = WDAGestures(client, session, fast_touch=True)
        gestures.tap(12, 34, portrait=True)
        self.assertEqual(client.post.call_args.args[0], "/session/sid/wda/fastTap")
        client.post.reset_mock()
        gestures.tap(12, 34, portrait=False)
        self.assertEqual(client.post.call_args.args[0], "/session/sid/actions")
        client.post.reset_mock()
        client.post.return_value = {"value": {"completed": False}}
        with self.assertRaises(WDAError):
            gestures.tap(12, 34, portrait=True)
        client.post.assert_called_once()

    def test_fast_touch_timeout_does_not_repeat_or_fall_back(self):
        client, session = MagicMock(), MagicMock()
        session.ensure_session.return_value = "sid"
        session._window_size = (430, 932)
        client.post.side_effect = ConnectionError("uncertain")
        with self.assertRaises(ConnectionError):
            WDAGestures(client, session, fast_touch=True).tap(12, 34, portrait=True)
        client.post.assert_called_once()

    def test_disconnected_device_is_not_fabricated_from_saved_udid(self):
        discovery = DeviceDiscovery()
        with patch.object(discovery, "list_devices", return_value=[]):
            self.assertIsNone(discovery.get_default_device("configured-device"))

    def test_tap_uses_touch_synthesis_without_animation_wait(self):
        client, session = MagicMock(), MagicMock()
        session.ensure_session.return_value = "sid"
        WDAGestures(client, session).tap(12, 34)
        self.assertEqual(client.post.call_args.args[0], "/session/sid/actions")
        actions = client.post.call_args.kwargs["json_data"]["actions"][0]["actions"]
        self.assertEqual([a["type"] for a in actions], ["pointerMove", "pointerDown", "pause", "pointerUp"])
        self.assertEqual(actions[0]["x"], 12)
        self.assertEqual(actions[2]["duration"], 20)

    def test_swipe_duration_is_finger_movement_time(self):
        client, session = MagicMock(), MagicMock()
        session.ensure_session.return_value = "sid"
        WDAGestures(client, session).swipe(1, 2, 3, 4, .15)
        actions = client.post.call_args.kwargs["json_data"]["actions"][0]["actions"]
        self.assertEqual(actions[2]["duration"], 150)
        self.assertEqual(actions[2]["x"], 3)
        self.assertNotIn("pause", [a["type"] for a in actions])

    def test_unsupported_actions_endpoint_falls_back_but_timeout_does_not(self):
        client, session = MagicMock(), MagicMock()
        session.ensure_session.return_value = "sid"
        client.post.side_effect = [WDAError("unsupported", 404, "unknown command"), {}]
        WDAGestures(client, session).tap(1, 2)
        self.assertEqual(client.post.call_args.args[0], "/session/sid/wda/tap")
        client.post.reset_mock()
        client.post.side_effect = ConnectionError("timeout")
        with self.assertRaises(ConnectionError):
            WDAGestures(client, session).tap(1, 2)
        client.post.assert_called_once()

    def test_timed_out_mutating_action_is_never_repeated(self):
        client = WDAClient(max_retries=3)
        client.session.request = MagicMock(side_effect=requests.ReadTimeout("timeout"))
        with self.assertRaises(ConnectionError):
            client.post("/actions")
        client.session.request.assert_called_once()

    def test_new_session_applies_low_latency_settings(self):
        client = MagicMock()
        client.post.side_effect = [{"sessionId": "sid"}, {"value": None}]
        session = WDASession(client)
        session.start()
        self.assertEqual(client.post.call_args.args[0], "/session/sid/appium/settings")
        self.assertEqual(client.post.call_args.kwargs["json_data"]["settings"]["animationCoolOffTimeout"], 0)

    def test_wda_errors_are_not_successful_results(self):
        for status in (200, 404):
            client = WDAClient()
            response = client.session.request = MagicMock()
            response.return_value.status_code = status
            response.return_value.text = "unsupported endpoint"
            response.return_value.json.return_value = {"value": {"error": "unknown command", "message": "unsupported endpoint"}}
            with self.assertRaises(WDAError):
                client.post("/unsupported")
            response.assert_called_once()

    def test_preview_is_resized_jpeg(self):
        ctrl = MagicMock()
        ctrl.screenshot.get_image.return_value = Image.new("RGB", (1290, 2796))
        with patch.object(server, "get_controller", return_value=ctrl):
            response = server.get_screen_preview()
        img = Image.open(io.BytesIO(response.body))
        self.assertEqual(img.format, "JPEG")
        self.assertLessEqual(img.width, 600)
        self.assertLessEqual(img.height, 1300)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_zero_swipe_destination_is_preserved(self):
        ctrl = MagicMock()
        ctrl.session._window_size = (430, 932)
        with patch.object(server, "get_controller", return_value=ctrl):
            server.action_swipe(server.SwipeRequest(norm_from_x=0.5, norm_from_y=0.5, norm_to_x=0, norm_to_y=0))
        ctrl.gestures.swipe.assert_called_once_with(215.0, 466.0, 0, 0, 0.4)

    def test_status_reuses_cached_dimensions(self):
        ctrl = MagicMock()
        ctrl.session._window_size = (430, 932)
        with patch.object(server, "get_controller", return_value=ctrl):
            server.get_all_status()
        ctrl.session.get_window_size.assert_not_called()
