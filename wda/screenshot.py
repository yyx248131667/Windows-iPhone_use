import base64
import io
import logging
from typing import Optional
from PIL import Image
from .client import WDAClient

logger = logging.getLogger(__name__)


class WDAScreenshot:
    """
    Handles capturing and processing screenshots from WebDriverAgent.
    """

    def __init__(self, client: WDAClient):
        self.client = client

    def get_base64(self) -> str:
        """Fetch raw base64 string of the current screen."""
        res = self.client.get("/screenshot")
        b64_str = res.get("value", "")
        if isinstance(b64_str, dict):
            b64_str = b64_str.get("raw", "")
        if not b64_str:
            raise RuntimeError(f"Empty screenshot response from WDA: {res}")
        return b64_str

    def get_bytes(self) -> bytes:
        """Fetch screenshot as raw PNG bytes."""
        b64_str = self.get_base64()
        return base64.b64decode(b64_str)

    def get_image(self) -> Image.Image:
        """Fetch screenshot as a PIL Image object."""
        png_bytes = self.get_bytes()
        return Image.open(io.BytesIO(png_bytes))

    def save(self, filepath: str) -> str:
        """Save screenshot directly to specified file path."""
        img = self.get_image()
        img.save(filepath)
        logger.info(f"Saved screenshot to {filepath}")
        return filepath
