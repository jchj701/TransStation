"""拖出负载与剪贴板读写（Qt 侧封装，统一为 kinds.RawPayload）。

约定：
- 本地文件 → QMimeData.setUrls（Qt 映射为 OLE CF_HDROP）
- 文本/链接 → setText + setHtml（CF_UNICODETEXT + CF_HTML）
- 位图 → setImageData（OLE CF_DIB，Qt 自动）
- 链接复制一律不带 urls，避免资源管理器把剪贴板误当文件清单
"""
from __future__ import annotations

from PySide6.QtCore import QBuffer, QMimeData, QUrl, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPixmap

from transstation.core.kinds import RawPayload
from transstation.store.db import Item


def image_to_png_bytes(image: QImage, max_side: int = 4096) -> bytes | None:
    """QImage → PNG 字节（超长边等比缩小到 max_side，防剪贴板/镜像超限）。"""
    if image.isNull():
        return None
    img = image
    if max(img.width(), img.height()) > max_side:
        img = image.scaled(
            max_side, max_side,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    if not img.save(buf, "PNG"):
        return None
    return bytes(buf.data())


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def text_mime(text: str, html: str | None = None) -> QMimeData:
    m = QMimeData()
    m.setText(text)
    if html:
        m.setHtml(html)
    return m


def url_mime(url: str, title: str = "") -> QMimeData:
    m = QMimeData()
    m.setText(url)
    m.setHtml(f'<a href="{_html_escape(url)}">{_html_escape(title or url)}</a>')
    return m


def files_mime(paths: list[str], with_text: bool = True) -> QMimeData:
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(p) for p in paths])
    if with_text:
        m.setText("\r\n".join(paths))
    return m


def image_mime(image: QImage) -> QMimeData:
    m = QMimeData()
    m.setImageData(image)
    return m


def mime_for_item(item: Item) -> QMimeData:
    """按条目类型构造拖出/复制负载。"""
    if item.kind in ("file", "image"):
        if item.path and _path_exists(item.path):
            m = files_mime([item.path])
            if item.kind == "image":
                _attach_image_preview(m, item.path)
            return m
        # 位图镜像（原路径丢失时仍可取出内容）
        if item.kind == "image" and item.image_file and _path_exists(item.image_file):
            m = files_mime([item.image_file])
            _attach_image_preview(m, item.image_file)
            return m
        return QMimeData()  # 路径失效
    if item.kind == "link":
        return url_mime(item.url or item.content, item.title or "")
    # text
    html = _plain_to_html(item.content)
    return text_mime(item.content, html)


def _path_exists(p: str) -> bool:
    from pathlib import Path

    return bool(p) and Path(p).exists()


def _attach_image_preview(m: QMimeData, path: str) -> None:
    """文件型图片同时附带位图，方便拖入不支持文件的应用。"""
    try:
        pix = QPixmap(path)
        if not pix.isNull():
            m.setImageData(pix.toImage())
    except Exception:
        pass


def _plain_to_html(text: str) -> str:
    lines = [_html_escape(ln) for ln in (text or "").splitlines()]
    return "<html><body>" + "<br>".join(lines) + "</body></html>"


def set_clipboard(m: QMimeData) -> bool:
    QGuiApplication.clipboard().setMimeData(m)
    return True


def read_clipboard_payload() -> RawPayload | None:
    """读取剪贴板为 RawPayload；空剪贴板返回 None。"""
    cb = QGuiApplication.clipboard()
    md = cb.mimeData()
    if md is None:
        return None
    files: list[str] = []
    if md.hasUrls():
        for u in md.urls():
            if u.isLocalFile():
                p = u.toLocalFile()
                if p:
                    files.append(p)
    text = md.text() if md.hasText() else None
    html = md.html() if md.hasHtml() else None
    image_bytes = None
    if md.hasImage():
        image_bytes = image_to_png_bytes(md.imageData())
    p = RawPayload(files=files, text=text, html=html, image_bytes=image_bytes)
    if not (p.files or (p.text or "").strip() or p.image_bytes):
        return None
    return p
