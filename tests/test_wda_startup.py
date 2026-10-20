import unittest
from unittest.mock import MagicMock, patch

from device.wda_runner import WDARunner
from device.tunnel import TunnelManager


class StartupTests(unittest.TestCase):
    def command(self, infos):
        runner = WDARunner(udid="target")
        http = MagicMock()
        http.__enter__.return_value = http
        http.get.return_value.json.return_value = infos
        with patch("device.wda_runner.requests.Session", return_value=http), patch.object(runner, "_get_help_text", return_value="runwda"):
            cmd, _ = runner.build_command()
        self.assertFalse(http.trust_env)
        return cmd

    def test_selects_target_userspace_tunnel(self):
        cmd = self.command([
            {"udid": "other", "address": "wrong", "rsdPort": 1},
            {"udid": "target", "address": "fd00::1", "rsdPort": 6000,
             "userspaceTun": True, "userspaceTunPort": 60106},
        ])
        self.assertEqual(cmd[cmd.index("--address") + 1], "fd00::1")
        self.assertEqual(cmd[cmd.index("--rsd-port") + 1], "6000")
        self.assertEqual(cmd[cmd.index("--userspace-port") + 1], "60106")

    def test_no_tunnel_keeps_legacy_command(self):
        self.assertNotIn("--address", self.command([]))

    def test_device_ide_failure_stops_waiting_immediately(self):
        runner = WDARunner()
        runner._last_logs = ["Failed to establish connection to the IDE: (null). Exiting."]
        with patch("device.wda_runner.requests.get") as request:
            self.assertFalse(runner.wait_for_ready(timeout_seconds=45))
            request.assert_not_called()

    def test_ios17_starts_and_stops_both_processes(self):
        manager = TunnelManager(udid="target", ios_version="26.2")
        tunnel, forward = MagicMock(), MagicMock()
        tunnel.poll.return_value = forward.poll.return_value = None
        http = MagicMock()
        http.__enter__.return_value = http
        http.get.return_value.json.return_value = [
            {"udid": "target", "address": "fd00::1", "rsdPort": 6000}]
        with patch("device.tunnel.subprocess.Popen", side_effect=[tunnel, forward]) as launch, patch("device.tunnel.threading.Thread"), patch("device.tunnel.time.sleep"), patch("device.tunnel.requests.Session", return_value=http):
            ok, msg = manager.start_tunnel()
            self.assertTrue(ok, msg)
            self.assertEqual(launch.call_args_list[1].args[0][1:],
                             ["forward", "8100", "8100", "--udid", "target"])
            self.assertTrue(manager.is_alive())
            manager.stop_tunnel()
        tunnel.terminate.assert_called_once()
        forward.terminate.assert_called_once()
        self.assertFalse(manager.is_alive())


if __name__ == "__main__":
    unittest.main()
