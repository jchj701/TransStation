"""镜像文件管理：文本镜像、位图镜像 PNG、缩略图缓存、条目文件清理。

数据目录内的文件布局：
  data/images/<id>.png       位图拖入/复制的本地镜像（该文件是条目的内容本体）
  data/images/thumbs/<id>.png 缩略图缓存（可由源路径随时重建）
  data/text/<id>.txt          文本镜像（开关控制，仅镜像非缓存）
"""
from __future__ import annotations

from pathlib import Path

from transstation.resources.tokens import LIMITS
from transstation.store.db import Item
from transstation import paths


def _dirs() -> dict[str, Path]:
    return paths.sub_dirs()


def text_mirror_path(item_id: int) -> Path:
    return _dirs()["text"] / f"{item_id}.txt"


def image_mirror_path(item_id: int) -> Path:
    return _dirs()["images"] / f"{item_id}.png"


def thumb_path(item_id: int) -> Path:
    return _dirs()["images"] / "thumbs" / f"{item_id}.png"


def write_text_mirror(item_id: int, content: str) -> Path:
    p = text_mirror_path(item_id)
    p.write_text(content, encoding="utf-8")
    return p


def write_image_mirror(item_id: int, png_bytes: bytes) -> Path:
    p = image_mirror_path(item_id)
    p.write_bytes(png_bytes)
    return p


def ensure_thumbnail(item: Item) -> Path | None:
    """为图片条目生成缩略图缓存（源文件缺失/解码失败返回 None）。"""
    if item.kind != "image":
        return None
    dst = thumb_path(item.id)
    if dst.exists():
        return dst
    src = Path(item.path or item.image_file)
    if not src.is_file():
        return None
    try:
        _render_thumb(src, dst)
        return dst if dst.exists() else None
    except Exception:
        return None


def _render_thumb(src: Path, dst: Path) -> None:
    from PySide6.QtCore import QRect, QSize, Qt
    from PySide6.QtGui import QImageReader, QPainter, QPixmap

    size = LIMITS["thumb_size"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    reader = QImageReader(str(src))
    reader.setAutoTransform(True)
    reader.setScaledSize(_fit_size(reader.size(), size))
    image = reader.read()
    if image.isNull():
        # svg 等 QImageReader 不支持的格式走 QPixmap 兜底
        pix = QPixmap(str(src))
        if pix.isNull():
            return
        pix = pix.scaled(
            _fit_size(pix.size(), size),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if not pix.save(str(dst), "PNG"):
            dst.unlink(missing_ok=True)
        return
    if not image.save(str(dst), "PNG"):
        dst.unlink(missing_ok=True)


def _fit_size(size, cap: int):
    from PySide6.QtCore import QSize

    w, h = size.width(), size.height()
    if w <= 0 or h <= 0:
        return QSize(cap, cap)
    if w >= h:
        return QSize(cap, max(1, round(h * cap / w)))
    return QSize(max(1, round(w * cap / h)), cap)


def cleanup_item_files(item: Item) -> None:
    """物理删除条目在本数据目录内的镜像/缩略图（绝不触碰用户原文件）。"""
    for p in (text_mirror_path(item.id), thumb_path(item.id), image_mirror_path(item.id)):
        try:
            if p.is_file():
                p.unlink()
        except OSError:
            pass
