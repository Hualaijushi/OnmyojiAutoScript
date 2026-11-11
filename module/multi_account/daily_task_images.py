"""协作任务截图的传递及 HTML 内嵌图片恢复。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


ImageKey = tuple[str, str, str, str]
_DATA_IMAGE = re.compile(r"data:image/(?:jpeg|png);base64,[A-Za-z0-9+/]+={0,2}")


@dataclass(frozen=True, slots=True)
class CooperationImage:
    slot: int
    label: str
    data_uri: str

    def valid(self) -> bool:
        return (
            self.slot in {1, 2, 3}
            and isinstance(self.label, str)
            and isinstance(self.data_uri, str)
            and len(self.data_uri) <= 2_000_000
            and _DATA_IMAGE.fullmatch(self.data_uri) is not None
        )


@dataclass(frozen=True, slots=True)
class CooperationGallery:
    key: ImageKey
    images: tuple[CooperationImage, ...]


def read_cooperation_galleries(path: Path) -> dict[ImageKey, CooperationGallery]:
    """图片仅保存在日报中，后续实例刷新时从同一天 HTML 恢复。"""
    class ImageParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.images: dict[ImageKey, list[CooperationImage]] = {}

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag != "img" or "data-image-key" not in values:
                return
            try:
                key = json.loads(values["data-image-key"])
                picture = CooperationImage(
                    slot=int(values.get("data-slot", "")),
                    label=values.get("alt", ""),
                    data_uri=values.get("src", ""),
                )
            except (TypeError, ValueError):
                return
            if not isinstance(key, list) or len(key) != 4 or not all(isinstance(item, str) for item in key):
                return
            if key[0] not in {"cooperation_morning", "cooperation_evening"} or not picture.valid():
                return
            images = self.images.setdefault(tuple(key), [])
            if len(images) < 3 and all(item.slot != picture.slot for item in images):
                images.append(picture)

    try:
        content = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    parser = ImageParser()
    parser.feed(content)
    return {key: CooperationGallery(key, tuple(images)) for key, images in parser.images.items()}
