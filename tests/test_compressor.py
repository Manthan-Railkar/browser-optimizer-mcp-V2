from bs4 import BeautifulSoup
from app.compressor.compressor import compressor

def test_clean_dom(sample_login_html):
    soup = BeautifulSoup(sample_login_html, "lxml")
    cleaned = compressor.clean_dom(soup)
    
    # Header, footer, script, and style should be removed
    assert cleaned.find("header") is None
    assert cleaned.find("footer") is None
    assert cleaned.find("script") is None
    assert cleaned.find("style") is None
    
    # Form, inputs, labels, button, a should remain
    assert cleaned.find("form") is not None
    assert cleaned.find("input") is not None
    assert cleaned.find("button") is not None

def test_remove_empty():
    html = "<div><span></span><p>Hello</p></div>"
    soup = BeautifulSoup(html, "lxml")
    cleaned = compressor.remove_empty(soup)
    
    # Span is empty and has no kids, should be decomposed
    assert cleaned.find("span") is None
    assert cleaned.find("p") is not None
    assert cleaned.find("p").text == "Hello"

def test_extract_ui(sample_login_html):
    soup = BeautifulSoup(sample_login_html, "lxml")
    ui = compressor.extract_ui(soup)
    
    # 2 inputs, 1 button, 1 link (labels are also UI elements in IMPORTANT_TAGS)
    assert len(ui) >= 4
    
    tags = [el["tag"] for el in ui]
    assert "input" in tags
    assert "button" in tags
    assert "a" in tags
    
    # Find button and assert contents
    btn = next(el for el in ui if el["tag"] == "button")
    assert btn["text"] == "Log In"
    assert btn["id"] == "submit-btn"

def test_compress(sample_login_html):
    extracted = {
        "html": BeautifulSoup(sample_login_html, "lxml"),
        "ax_tree": {"name": "page"},
        "raw_html_length": len(sample_login_html),
        "url": "http://test.com",
        "title": "Test Title"
    }
    
    compressed = compressor.compress(extracted)
    assert "ui" in compressed
    assert "accessibility" in compressed or "ax_tree" in compressed
    assert compressed["url"] == "http://test.com"
    assert compressed["title"] == "Test Title"
    assert compressed["compression_ratio"] > 0
