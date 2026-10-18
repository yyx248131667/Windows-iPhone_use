import argparse
import logging
import os
import sys
import yaml

from device.discovery import DeviceDiscovery
from device.pairing import DevicePairing
from device.tunnel import TunnelManager
from device.wda_runner import WDARunner
from agent.controller import iPhoneController

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def load_config(config_path: str = "config/settings.yaml") -> dict:
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def cmd_discover(args, cfg):
    go_ios_bin = cfg.get("tools", {}).get("go_ios_bin", "ios")
    discovery = DeviceDiscovery(go_ios_bin=go_ios_bin)
    devices = discovery.list_devices()
    if not devices:
        print("\n❌ No iOS devices found. Please ensure your iPhone is connected via USB and screen unlocked.")
        return
    print(f"\n📱 Discovered {len(devices)} device(s):")
    for d in devices:
        tunnel_note = " (Requires iOS 17+ CoreDevice tunnel)" if d.is_ios_17_plus else " (Standard usbmux)"
        print(f"  - [{d.device_name}] UDID: {d.udid} | iOS: {d.product_version} | Type: {d.product_type}{tunnel_note}")


def cmd_tunnel(args, cfg):
    go_ios_bin = cfg.get("tools", {}).get("go_ios_bin", "ios")
    udid = args.udid or cfg.get("device", {}).get("udid")
    tunnel = TunnelManager(go_ios_bin=go_ios_bin, udid=udid)
    print("🚀 Starting iOS tunnel...")
    ok, msg = tunnel.start_tunnel()
    print(msg)
    if ok:
        print("Press Ctrl+C to stop tunnel...")
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            tunnel.stop_tunnel()
            print("\nTunnel stopped.")


def cmd_run_wda(args, cfg):
    go_ios_bin = cfg.get("tools", {}).get("go_ios_bin", "ios")
    dev_cfg = cfg.get("device", {})
    wda_cfg = cfg.get("wda", {})
    runner = WDARunner(
        go_ios_bin=go_ios_bin,
        udid=args.udid or dev_cfg.get("udid"),
        bundle_id=dev_cfg.get("bundle_id", "com.facebook.WebDriverAgentRunner.xctrunner"),
        testrunner_bundle_id=dev_cfg.get("testrunner_bundle_id", "com.facebook.WebDriverAgentRunner.xctrunner"),
        xctestrun_path=dev_cfg.get("xctestrun_path"),
        wda_base_url=wda_cfg.get("base_url", "http://127.0.0.1:8100"),
    )
    print("🚀 Launching WebDriverAgentRunner via XCTest...")
    ok, msg = runner.start(timeout_seconds=45)
    print(f"Result: {msg}")
    if ok:
        print("WDA server running. Press Ctrl+C to terminate...")
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            runner.stop()
            print("\nWDA runner stopped.")


def cmd_screenshot(args, cfg):
    output_path = args.output or "screenshot.png"
    ctrl = iPhoneController(config=cfg, udid=args.udid)
    print(f"📸 Capturing screenshot from device to {output_path}...")
    try:
        ctrl.screenshot.save(output_path)
        print(f"✅ Screenshot saved successfully to {os.path.abspath(output_path)}")
    except Exception as e:
        print(f"❌ Failed to capture screenshot: {e}")


def cmd_server(args, cfg):
    import uvicorn
    srv_cfg = cfg.get("server", {})
    host = args.host or srv_cfg.get("host", "127.0.0.1")
    port = args.port or srv_cfg.get("port", 8000)
    print(f"🚀 Starting Windows-iPhone_use FastAPI server at http://{host}:{port}")
    uvicorn.run("api.server:app", host=host, port=port, reload=srv_cfg.get("reload", False))


def cmd_init(args, cfg):
    ctrl = iPhoneController(config=cfg, udid=args.udid)
    ok, msg = ctrl.initialize()
    if ok:
        print(f"\n🎉 Success: {msg}")
    else:
        print(f"\n❌ Initialization failed: {msg}")


def main():
    parser = argparse.ArgumentParser(description="Windows-iPhone_use CLI")
    parser.add_argument("--config", default="config/settings.yaml", help="Path to settings.yaml")
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # discover
    subparsers.add_parser("discover", help="Discover connected iPhone devices")

    # tunnel
    t_parser = subparsers.add_parser("tunnel", help="Start tunnel for iOS 17+")
    t_parser.add_argument("--udid", help="Device UDID")

    # run-wda
    w_parser = subparsers.add_parser("run-wda", help="Start WDA runner via XCTest")
    w_parser.add_argument("--udid", help="Device UDID")

    # screenshot
    s_parser = subparsers.add_parser("screenshot", help="Capture screenshot")
    s_parser.add_argument("--udid", help="Device UDID")
    s_parser.add_argument("-o", "--output", default="screenshot.png", help="Output file path")

    # server
    srv_parser = subparsers.add_parser("server", help="Start FastAPI HTTP server")
    srv_parser.add_argument("--host", help="Server host")
    srv_parser.add_argument("--port", type=int, help="Server port")

    # init
    init_parser = subparsers.add_parser("init", help="Verify full connection, tunnel, and WDA pipeline")
    init_parser.add_argument("--udid", help="Device UDID")

    args = parser.parse_args()
    cfg = load_config(args.config)

    if args.command == "discover":
        cmd_discover(args, cfg)
    elif args.command == "tunnel":
        cmd_tunnel(args, cfg)
    elif args.command == "run-wda":
        cmd_run_wda(args, cfg)
    elif args.command == "screenshot":
        cmd_screenshot(args, cfg)
    elif args.command == "server":
        cmd_server(args, cfg)
    elif args.command == "init":
        cmd_init(args, cfg)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
