"""
Device management module for Windows-iPhone_use.
Handles discovery, pairing, iOS 17+ tunneling, installation, and XCTest/WDA startup.
"""

from .discovery import DeviceDiscovery, DeviceInfo
from .pairing import DevicePairing
from .tunnel import TunnelManager
from .installer import AppInstaller
from .wda_runner import WDARunner

__all__ = [
    "DeviceDiscovery",
    "DeviceInfo",
    "DevicePairing",
    "TunnelManager",
    "AppInstaller",
    "WDARunner",
]
