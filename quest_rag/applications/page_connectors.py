"""URL-based external business page onboarding for the configuration Agent."""

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

CONNECTOR_DIR = Path(__file__).with_name("page_connectors")


class _FormParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.fields = []; self._label = ""; self._select = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "label": self._label = ""
        if tag in {"input", "select", "textarea", "button"}:
            key = attrs.get("name") or attrs.get("id") or attrs.get("type")
            if key:
                self.fields.append({"key": key, "label": self._label.strip() or key, "element": tag, "type": attrs.get("type", "text"), "required": "required" in attrs})
        if tag == "select": self._select = self.fields[-1] if self.fields else None

    def handle_data(self, data):
        if self._label is not None: self._label += data

    def handle_endtag(self, tag):
        if tag == "label": self._label = ""
        if tag == "select": self._select = None


def analyze_page(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "QuestRAG Business Config Agent/1.0"})
    with urlopen(request, timeout=12) as response:
        html = response.read(2_000_000).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    parser = _FormParser(); parser.feed(html)
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return {"entry_url": url, "title": re.sub(r"\s+", " ", title.group(1)).strip() if title else url, "fields": parser.fields, "requires_manual_mapping": not bool(parser.fields)}


def save_connector(business_code: str, name: str, analysis: dict) -> dict:
    CONNECTOR_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"business_code": business_code, "name": name, "version": "1.0.0", **analysis, "status": "published"}
    (CONNECTOR_DIR / f"{business_code}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def list_connectors() -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in CONNECTOR_DIR.glob("*.json")] if CONNECTOR_DIR.exists() else []
