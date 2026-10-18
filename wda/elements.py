import logging
from typing import Any, Dict, List, Optional
from .client import WDAClient
from .session import WDASession

logger = logging.getLogger(__name__)


class UIElement:
    def __init__(self, client: WDAClient, session: WDASession, element_id: str):
        self.client = client
        self.session = session
        self.element_id = element_id

    def click(self) -> Dict[str, Any]:
        sid = self.session.ensure_session()
        return self.client.post(f"/session/{sid}/element/{self.element_id}/click")

    def type_text(self, text: str) -> Dict[str, Any]:
        sid = self.session.ensure_session()
        return self.client.post(f"/session/{sid}/element/{self.element_id}/value", json_data={"value": list(text)})

    def clear(self) -> Dict[str, Any]:
        sid = self.session.ensure_session()
        return self.client.post(f"/session/{sid}/element/{self.element_id}/clear")

    def get_attribute(self, name: str) -> Any:
        sid = self.session.ensure_session()
        res = self.client.get(f"/session/{sid}/element/{self.element_id}/attribute/{name}")
        return res.get("value")

    def get_rect(self) -> Dict[str, float]:
        sid = self.session.ensure_session()
        res = self.client.get(f"/session/{sid}/element/{self.element_id}/rect")
        return res.get("value", {})

    @property
    def text(self) -> str:
        sid = self.session.ensure_session()
        res = self.client.get(f"/session/{sid}/element/{self.element_id}/text")
        return res.get("value", "")


class WDAElements:
    """
    Manages querying the UI hierarchy and locating elements.
    """

    def __init__(self, client: WDAClient, session: WDASession):
        self.client = client
        self.session = session

    def get_source(self, format_type: str = "xml") -> Any:
        """
        Fetch accessibility hierarchy source tree.
        format_type can be 'xml' or 'json' (if supported by WDA config).
        """
        sid = self.session.ensure_session()
        res = self.client.get(f"/session/{sid}/source?format={format_type}")
        return res.get("value")

    def find_element(self, using: str, value: str) -> Optional[UIElement]:
        """
        Find single element.
        `using` can be: 'xpath', 'name', 'class name', 'predicate string', 'class chain'.
        """
        sid = self.session.ensure_session()
        res = self.client.post(
            f"/session/{sid}/element",
            json_data={"using": using, "value": value},
        )
        val = res.get("value", {})
        if isinstance(val, dict) and "ELEMENT" in val:
            return UIElement(self.client, self.session, val["ELEMENT"])
        return None

    def find_elements(self, using: str, value: str) -> List[UIElement]:
        """Find multiple elements."""
        sid = self.session.ensure_session()
        res = self.client.post(
            f"/session/{sid}/elements",
            json_data={"using": using, "value": value},
        )
        elements = []
        for item in res.get("value", []):
            if isinstance(item, dict) and "ELEMENT" in item:
                elements.append(UIElement(self.client, self.session, item["ELEMENT"]))
        return elements

    def find_by_text(self, text: str) -> Optional[UIElement]:
        """Shortcut to find element matching text/label by predicate or xpath."""
        predicate = f"label == '{text}' OR name == '{text}' OR value == '{text}'"
        return self.find_element("predicate string", predicate)
