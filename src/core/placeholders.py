from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Tuple

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

INLINE_TAGS = {
    "a",
    "abbr",
    "b",
    "br",
    "cite",
    "code",
    "em",
    "i",
    "mark",
    "small",
    "span",
    "strong",
    "sub",
    "sup",
    "u",
}

PLACEHOLDER_OPEN_TEMPLATE = "<ph data-id=\"{token}\">"
PLACEHOLDER_CLOSE_TEMPLATE = "</ph>"


@dataclass(frozen=True)
class PlaceholderSpec:
    tag: str
    attrs: Dict[str, str]

    def build_open_tag(self) -> str:
        attrs = "".join(
            f" {name}='{value}'" for name, value in sorted(self.attrs.items())
        )
        return f"<{self.tag}{attrs}>"

    def build_close_tag(self) -> str:
        return f"</{self.tag}>"


class PlaceholderEncoder:

    def __init__(self) -> None:
        self._counter = 0

    def encode_fragment(self, html_fragment: str) -> Tuple[str, Dict[str, PlaceholderSpec]]:
        """Replace inline tags with placeholders, returning clean text and mapping."""
        if "<" not in html_fragment:
            return html_fragment, {}
        soup = BeautifulSoup(html_fragment, "html.parser")
        mapping: Dict[str, PlaceholderSpec] = {}
        encoded_parts: list[str] = []
        for element in soup.contents:
            encoded_parts.append(self._encode_node(element, mapping))
        return "".join(encoded_parts), mapping

    def decode_fragment(self, text: str, mapping: Dict[str, PlaceholderSpec]) -> str:
        """Rebuild original inline tags by interpreting <ph data-id="..."> wrappers.

        We parse the fragment as HTML and replace each <ph> with the corresponding
        original tag and attributes from the mapping, preserving children.
        """
        if "<ph" not in text:
            return text
        soup = BeautifulSoup(text, "html.parser")
        for ph in soup.find_all("ph"):
            token = ph.get("data-id")
            if not token:
                continue
            spec = mapping.get(token)
            if not spec:
                continue
            # Build a new tag with same children
            new_tag = soup.new_tag(spec.tag)
            for k, v in spec.attrs.items():
                new_tag.attrs[k] = v
            # Move children
            for child in list(ph.children):
                new_tag.append(child.extract())
            ph.replace_with(new_tag)

        return str(soup)

    def _encode_node(self, node, mapping: Dict[str, PlaceholderSpec]) -> str:
        if isinstance(node, NavigableString):
            return str(node)
        if isinstance(node, Tag):
            if node.name not in INLINE_TAGS:
                encoded_children = [self._encode_node(child, mapping) for child in node.children]
                return "".join(encoded_children)
            token = self._next_token()
            mapping[token] = PlaceholderSpec(
                tag=node.name,
                attrs={k: str(v) for k, v in node.attrs.items()},
            )
            encoded_children = [self._encode_node(child, mapping) for child in node.children]
            open_token = PLACEHOLDER_OPEN_TEMPLATE.format(token=token)
            close_token = PLACEHOLDER_CLOSE_TEMPLATE.format(token=token)
            return f"{open_token}{''.join(encoded_children)}{close_token}"
        return ""

    def _next_token(self) -> str:
        self._counter += 1
        return f"PH{self._counter:04d}"
