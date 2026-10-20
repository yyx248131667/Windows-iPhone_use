"""Compare confirmed fastTap and standard actions on a locally signed candidate.

Run on an unlocked portrait Home screen and choose a harmless point explicitly.
Never retries an action whose completion is uncertain.
"""
import argparse
import json
from pathlib import Path
import statistics
import time

import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web", default="http://127.0.0.1:8000")
    parser.add_argument("--x", required=True, type=float)
    parser.add_argument("--y", required=True, type=float)
    parser.add_argument("--samples", type=int, default=5, choices=range(1, 21))
    parser.add_argument("--output", type=Path, default=Path("artifacts/fast-touch-benchmark.json"))
    args = parser.parse_args()
    with requests.Session() as http:
        http.trust_env = False
        state = http.get(args.web.rstrip("/") + "/api/status/all", timeout=5)
        state.raise_for_status()
        state = state.json()
        if not state["wda"]["online"] or not state["session"]["active"]:
            raise SystemExit("WDA session is offline")
        base = state["wda"]["base_url"].rstrip("/")
        sid = state["session"]["session_id"]
        size = http.get(f"{base}/session/{sid}/window/size", timeout=5)
        size.raise_for_status()
        size = size.json()["value"]
        orientation = http.get(f"{base}/session/{sid}/orientation", timeout=5)
        orientation.raise_for_status()
        if orientation.json()["value"] != "PORTRAIT" or size["width"] > size["height"]:
            raise SystemExit("Portrait Home screen required")
        if not (0 <= args.x < size["width"] and 0 <= args.y < size["height"]):
            raise SystemExit("Point outside viewport")
        results = {"fast": [], "standard": []}
        payloads = {
            "fast": ("/wda/fastTap", {"x": args.x, "y": args.y, **size, "orientation": 1}),
            "standard": ("/actions", {"actions": [{"type": "pointer", "id": "finger",
                "parameters": {"pointerType": "touch"}, "actions": [
                    {"type": "pointerMove", "origin": "viewport", "x": round(args.x), "y": round(args.y), "duration": 0},
                    {"type": "pointerDown", "button": 0}, {"type": "pause", "duration": 20},
                    {"type": "pointerUp", "button": 0}]}]})}
        for _ in range(args.samples):
            for mode, (path, payload) in payloads.items():
                started = time.perf_counter()
                response = http.post(f"{base}/session/{sid}{path}", json=payload, timeout=15)
                elapsed = (time.perf_counter() - started) * 1000
                response.raise_for_status()
                value = response.json().get("value")
                if isinstance(value, dict) and value.get("error"):
                    raise SystemExit("Action failed; inspect phone before continuing: " + str(value))
                if mode == "fast" and not (isinstance(value, dict) and value.get("completed") is True):
                    raise SystemExit("Missing real completion confirmation")
                results[mode].append({"http_ms": elapsed, "device": value})
                print(mode, round(elapsed, 1), "ms", flush=True)
                time.sleep(.2)
        summary = {mode: {"median_ms": statistics.median(x["http_ms"] for x in values),
                          "max_ms": max(x["http_ms"] for x in values)} for mode, values in results.items()}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"summary": summary, "samples": results}, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
