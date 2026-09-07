"""内容解析与类型识别（纯逻辑，可单测）。

输入统一为 RawPayload（文件路径列表 / 文本 / html / 位图字节），
输出为 RawEntry 列表（待入库条目）。
"""
from __future__ import annotations

import html as html_mod
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from transstation.resources.tokens import LIMITS
from transstation.store.db import KINDS

IMAGE_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico",
    ".tif", ".tiff", ".svg", ".avif", ".jfif",
}

_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_ANCHOR_RE = re.compile(r"<a\s[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_IMG_TAG_RE = re.compile(r"<img\b", re.IGNORECASE)


@dataclass
class RawPayload:
    """从拖放/剪贴板取到的原始内容。"""
    files: list[str] = field(default_factory=list)   # 本地路径（含目录）
    text: str | None = None
    html: str | None = None
    image_bytes: bytes | None = None


@dataclass
class RawEntry:
    """一条待入库内容。"""
    kind: str
    title: str = ""
    content: str = ""
    path: str = ""
    url: str = ""
    image_bytes: bytes | None = None   # 位图来源：需镜像为 PNG
    flags: str = ""


def is_image_path(p: str) -> bool:
    try:
        return Path(p).suffix.lower() in IMAGE_EXTS
    except Exception:
        return False


def looks_like_url(text: str) -> bool:
    return bool(_URL_RE.match((text or "").strip()))


def _clean_html(s: str) -> str:
    s = _TAG_RE.sub("", s or "")
    return html_mod.unescape(s).strip()


def _anchor_from_html(h: str) -> tuple[str, str] | None:
    """从 CF_HTML 中取第一个 <a href>，返回 (url, 文本)。"""
    m = _ANCHOR_RE.search(h or "")
    if not m:
        return None
    url = html_mod.unescape(m.group(1)).strip()
    text = _clean_html(m.group(2))
    return url, text


def _strip_line(s: str) -> str:
    lines = [ln.strip() for ln in (s or "").splitlines() if ln.strip()]
    return lines[0] if lines else ""


def _first_line_as_title(text: str) -> str:
    line = _strip_line(text)
    return line[:60]


def parse_payload(p: RawPayload) -> list[RawEntry]:
    """统一入口：文件 → 文本 → 链接 → 位图 → 空。"""
    # 1) 本地文件（可多个；目录也作为文件条目）
    if p.files:
        entries: list[RawEntry] = []
        for f in p.files:
            f = f.strip("\x00 ")
            if not f:
                continue
            path = Path(f)
            name = path.name or f
            is_dir = path.is_dir() if path.exists() else False
            if is_image_path(f) and not is_dir:
                entries.append(RawEntry("image", title=name, path=f))
            else:
                entries.append(
                    RawEntry("file", title=name, path=f, flags="dir" if is_dir else "")
                )
        return entries

    # 2) 富文本/链接类
    if p.html and _IMG_TAG_RE.search(p.html) and p.image_bytes:
        return [RawEntry("image", title=_image_title(p.html), image_bytes=p.image_bytes)]
    if p.html and p.image_bytes and not p.text:
        return [RawEntry("image", title=_image_title(p.html), image_bytes=p.image_bytes)]
    if p.image_bytes and not (p.text or "").strip():
        return [RawEntry("image", title="图片", image_bytes=p.image_bytes)]

    # 2b) 只带 <img src="file:///..."> 的拖拽（Snipaste 类截图工具常见）：
    #     无位图时按本地图片文件识别
    if p.html and not p.files and not p.image_bytes and not (p.text or "").strip():
        file_imgs = _img_file_srcs(p.html)
        if file_imgs:
            return [RawEntry("image", title=Path(f).name, path=f) for f in file_imgs]

    text = (p.text or "").strip("\x00 \n\r\t")
    if not text:
        return []

    # 链接：锚文本优先，其次整体即 URL
    anchor = _anchor_from_html(p.html) if p.html else None
    if anchor and anchor[0] and looks_like_url(anchor[0]):
        title = (anchor[1][:80] or anchor[0][:80]) or None
        return [RawEntry("link", title=title or _url_title(anchor[0]), url=anchor[0], content=anchor[0])]
    if looks_like_url(text):
        return [RawEntry("link", title=_url_title(text), url=text, content=text)]

    # 3) 纯文本
    title = _first_line_as_title(text)
    return [RawEntry("text", title=title, content=_truncate(text))]


def _image_title(html_text: str | None) -> str:
    """位图拖入/复制的默认标题。"""
    m = re.search(r"alt=\"([^\"]*)\"", html_text or "")
    alt = m.group(1).strip() if m else ""
    return (alt[:60] or f"图片 {datetime.now().strftime('%H:%M:%S')}")


_FILE_SRC_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)


def _img_file_srcs(html_text: str) -> list[str]:
    """从 <img src="file:///C:/x.png"> 提取存在的本地图片路径。"""
    from urllib.parse import unquote, urlparse

    out: list[str] = []
    for m in _FILE_SRC_RE.finditer(html_text or ""):
        src = html_mod.unescape(m.group(1)).strip()
        if not src:
            continue
        parsed = urlparse(src)
        if parsed.scheme.lower() == "file":
            p = unquote(parsed.path)
            if p.startswith("/") and ":" in p[:4]:   # /C:/x → C:/x
                p = p[1:]
        else:
            p = src
        try:
            path = Path(p)
            if path.is_file() and is_image_path(str(path)):
                out.append(str(path))
        except Exception:
            continue
        if out:
            break
    return out[:5]


def _truncate(text: str) -> str:
    cap = LIMITS["text_max_chars"]
    return text if len(text) <= cap else text[:cap] + "…（内容过长已截断）"


def _url_title(url: str) -> str:
    from urllib.parse import urlparse

    try:
        u = urlparse(url)
        host = u.netloc or url
        return f"{host}{u.path[:40]}" if len(host) < 80 else host[:80]
    except Exception:
        return url[:120]


def url_title(url: str) -> str:
    """供链接条目显式使用。"""
    return _url_title(url)
