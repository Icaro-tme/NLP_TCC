from __future__ import annotations

import os
import requests
from typing import Optional


class LibreTranslateClient:
    """Thin client for LibreTranslate HTTP API.

    Default base URL can be configured via env `LIBRETRANSLATE_URL`.
    Public instance: https://libretranslate.com (subject to rate limits).
    """

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = (base_url or os.getenv("LIBRETRANSLATE_URL") or "http://localhost:5000").rstrip("/")
        self.api_key = api_key or os.getenv("LIBRETRANSLATE_API_KEY")

    def translate(self, text: str, source_lang: str = "pt", target_lang: str = "en") -> str:
        url = f"{self.base_url}/translate"
        payload = {
            "q": text,
            "source": source_lang,
            "target": target_lang,
            "format": "text",
        }
        if self.api_key:
            payload["api_key"] = self.api_key
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        # API returns either {translatedText: ...} or a list; handle both
        if isinstance(data, dict) and "translatedText" in data:
            return data["translatedText"]
        if isinstance(data, list) and data and isinstance(data[0], dict) and "translatedText" in data[0]:
            return data[0]["translatedText"]
        return ""
