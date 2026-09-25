#!/usr/bin/env python3
"""Refresh the static publication snapshot from a public Google Scholar profile."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

PROFILE_ID = "lI38UZoAAAAJ"
PROFILE_URL = f"https://scholar.google.com/citations?user={PROFILE_ID}&hl=en&pagesize=100"
OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "publications.json"


class ScholarParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.publications: list[dict[str, object]] = []
        self.current: dict[str, object] | None = None
        self.capture: str | None = None
        self.buffer: list[str] = []
        self.gray_fields: list[str] = []

    @staticmethod
    def classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        return set(dict(attrs).get("class", "").split())

    def start_capture(self, name: str) -> None:
        self.capture, self.buffer = name, []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes, values = self.classes(attrs), dict(attrs)
        if tag == "tr" and "gsc_a_tr" in classes:
            self.current, self.gray_fields = {}, []
        elif self.current is not None and tag == "a" and "gsc_a_at" in classes:
            self.current["url"] = urljoin("https://scholar.google.com", values.get("href", ""))
            self.start_capture("title")
        elif self.current is not None and tag == "div" and "gs_gray" in classes:
            self.start_capture("gray")
        elif self.current is not None and ("gsc_a_ac" in classes or "gsc_a_h" in classes):
            self.start_capture("citations" if "gsc_a_ac" in classes else "year")

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.current is None:
            return
        if self.capture and ((self.capture == "title" and tag == "a") or (self.capture == "gray" and tag == "div") or (self.capture in {"citations", "year"} and tag in {"a", "span"})):
            value = " ".join("".join(self.buffer).split())
            if self.capture == "gray":
                self.gray_fields.append(value)
            else:
                self.current[self.capture] = value
            self.capture, self.buffer = None, []
        if tag == "tr":
            title = str(self.current.get("title", ""))
            if title:
                publication = self.current
                publication["citations"] = int(re.sub(r"\D", "", str(publication.get("citations", "0"))) or 0)
                publication["year"] = str(publication.get("year", ""))
                publication["venue"] = abbreviate_venue(self.gray_fields[1] if len(self.gray_fields) > 1 else "Publication")
                self.publications.append(publication)
            self.current = None


def abbreviate_venue(value: str) -> str:
    lower = value.lower()
    if "electron device letters" in lower:
        return "IEEE EDL"
    if "electron devices meeting" in lower:
        return "IEDM"
    if "mask and lithography" in lower:
        return "Proc. SPIE"
    if "electrochemical society" in lower:
        return "ECS Trans."
    return value.split(",")[0][:50] or "Publication"


def main() -> None:
    request = Request(PROFILE_URL, headers={"User-Agent": "Mozilla/5.0 (compatible; personal-site-publication-refresh/1.0)"})
    with urlopen(request, timeout=30) as response:
        parser = ScholarParser()
        parser.feed(response.read().decode("utf-8"))
    if not parser.publications:
        raise RuntimeError("Google Scholar returned no publication rows; keeping the existing snapshot")
    parser.publications.sort(key=lambda item: (-int(item["citations"]), str(item["title"])))
    payload = {"source": PROFILE_URL, "updated_at": datetime.now(timezone.utc).isoformat(), "publications": parser.publications}
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {len(parser.publications)} publications in {OUTPUT}")


if __name__ == "__main__":
    main()
