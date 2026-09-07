"""kinds.parse_payload 纯逻辑测试：类型识别与标题提取。"""
from transstation.core.kinds import RawPayload, parse_payload


def test_local_files():
    entries = parse_payload(RawPayload(files=[r"C:\x\a.txt", r"C:\x\b.png"]))
    assert [e.kind for e in entries] == ["file", "image"]
    assert entries[0].path == r"C:\x\a.txt"
    assert entries[0].title == "a.txt"


def test_directory_becomes_file_with_dir_flag(tmp_path):
    d = tmp_path / "some-folder"
    d.mkdir()
    entries = parse_payload(RawPayload(files=[str(d)]))
    assert entries[0].kind == "file"
    assert entries[0].flags == "dir"
    assert entries[0].title == d.name


def test_drag_html_anchor_link():
    """从浏览器拖链接：CF_HTML 里有 <a href>，应识别为 link 并取锚文本作标题。"""
    html = (
        '<HTML><BODY><!--StartFragment-->'
        '<a href="https://example.com/doc">示例文档标题</a>'
        "<!--EndFragment--></BODY></HTML>"
    )
    entries = parse_payload(RawPayload(text="https://example.com/doc", html=html))
    assert len(entries) == 1
    e = entries[0]
    assert e.kind == "link"
    assert e.url == "https://example.com/doc"
    assert e.title == "示例文档标题"


def test_whole_text_is_url_becomes_link():
    entries = parse_payload(RawPayload(text="https://example.com/page?q=1"))
    assert entries[0].kind == "link"
    assert entries[0].url == "https://example.com/page?q=1"


def test_plain_text_with_url_inside_stays_text():
    text = "参考 https://example.com 这篇文档，注意大小写。"
    entries = parse_payload(RawPayload(text=text))
    assert entries[0].kind == "text"
    assert entries[0].content == text
    # 标题取首行截断
    assert entries[0].title == text[:60]


def test_chrome_image_drag_alt_title():
    html = '<html><body><img src="file:///x.png" alt="截图示例"></body></html>'
    entries = parse_payload(RawPayload(html=html, image_bytes=b"\x89PNG-fake"))
    assert entries[0].kind == "image"
    assert entries[0].title == "截图示例"
    assert entries[0].image_bytes == b"\x89PNG-fake"


def test_image_without_alt_gets_clock_title():
    entries = parse_payload(RawPayload(image_bytes=b"\x89PNG-fake"))
    assert entries[0].kind == "image"
    assert entries[0].title.startswith("图片")


def test_html_img_file_src_fallback(tmp_path):
    """Snipaste 类：拖拽只带 <img src=file:///...>（无位图无文本）。"""
    from pathlib import Path

    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG minimal")
    html = f'<html><body><img src="file:///{str(img).replace(chr(92), "/")}"></body></html>'
    entries = parse_payload(RawPayload(html=html))
    assert len(entries) == 1
    assert entries[0].kind == "image"
    assert Path(entries[0].path) == img


def test_html_img_file_missing_ignored():
    html = '<html><body><img src="file:///C:/no/such/xx.png"></body></html>'
    assert parse_payload(RawPayload(html=html)) == []


def test_empty_payload_yields_nothing():
    assert parse_payload(RawPayload()) == []
    assert parse_payload(RawPayload(text="  \n ")) == []


def test_text_truncated_to_cap():
    text = "长" * 300_000
    entries = parse_payload(RawPayload(text=text))
    assert len(entries[0].content) <= 200_100  # 上限 + 截断提示
    assert "已截断" in entries[0].content


def test_files_win_out_over_text():
    """剪贴板里同有文件清单与文本时，文件优先。"""
    entries = parse_payload(RawPayload(files=[r"C:\x\c.txt"], text="hello"))
    assert [e.kind for e in entries] == ["file"]
