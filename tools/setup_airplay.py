"""Build the optional UxPlay Windows runtime locally (no machine-wide installer).

Run from the repository root with Python 3.12+ and git installed.
Downloads MSYS2 from its official release and UxPlay from its upstream repository.
"""
import hashlib
import os
import shlex
from pathlib import Path
import subprocess
import sys
import tarfile
import requests

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / ".runtime" / "airplay"
# Pin the upstream revision with built-in mDNS support (no Bonjour SDK needed).
UXPLAY_REF = "d9e293da6d5276315af6820d10542a859bbc3424"
PACKAGES = ["cmake", "gcc", "ninja", "libplist", "gstreamer", "gst-plugins-base",
            "gst-plugins-good", "gst-plugins-bad", "gst-libav"]


def run(args, **kwargs):
    subprocess.run(args, check=True, **kwargs)


def main():
    if os.name != "nt":
        raise SystemExit("On Linux/macOS, install UxPlay and GStreamer using upstream instructions.")
    if not hasattr(tarfile, "data_filter"):
        raise SystemExit("Use Python 3.12+ for safe portable-runtime extraction.")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    bash = RUNTIME / "msys64/usr/bin/bash.exe"
    if not bash.exists():
        response = requests.get("https://api.github.com/repos/msys2/msys2-installer/releases/latest", timeout=30)
        response.raise_for_status()
        asset = next(a for a in response.json()["assets"]
                     if a["name"].startswith("msys2-base-x86_64-") and a["name"].endswith(".tar.xz"))
        archive = RUNTIME / asset["name"]
        print("Downloading portable MSYS2...", flush=True)
        with requests.get(asset["browser_download_url"], stream=True, timeout=60) as download:
            download.raise_for_status()
            with archive.open("wb") as output:
                for chunk in download.iter_content(1024 * 1024):
                    output.write(chunk)
        digest = asset.get("digest", "")
        if digest.startswith("sha256:"):
            if hashlib.sha256(archive.read_bytes()).hexdigest() != digest.split(":", 1)[1]:
                raise SystemExit("MSYS2 download checksum mismatch")
        with tarfile.open(archive) as source:
            source.extractall(RUNTIME, filter="data")
    env = os.environ.copy()
    env.update(MSYSTEM="UCRT64", CHERE_INVOKING="1")
    packages = " ".join("mingw-w64-ucrt-x86_64-" + name for name in PACKAGES)
    print("Installing local compiler and media dependencies (about 2 GB installed)...", flush=True)
    run([str(bash), "-lc", "pacman -Sy --noconfirm --needed " + packages], env=env, cwd=ROOT)
    source = RUNTIME / "UxPlay"
    if not (source / ".git").exists():
        run(["git", "clone", "https://github.com/FDH2/UxPlay.git", str(source)])
    run(["git", "checkout", UXPLAY_REF], cwd=source)
    # Forward-slash drive paths are accepted by Windows CMake under MSYS2.
    source_path = source.as_posix()
    build = (source / "build").as_posix()
    prefix = (RUNTIME / "msys64/ucrt64").as_posix()
    command = " && ".join(shlex.join(args) for args in [
        ["cmake", "-S", source_path, "-B", build, "-G", "Ninja", "-DUSE_MDNS=1"],
        ["cmake", "--build", build, "-j", "4"],
        ["cmake", "--install", build, "--prefix", prefix],
    ])
    run([str(bash), "-lc", command], env=env, cwd=ROOT)
    print("AirPlay receiver ready. Start WebUI, then click Start AirPlay.")


if __name__ == "__main__":
    main()
