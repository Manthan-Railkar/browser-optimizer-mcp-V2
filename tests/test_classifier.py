from app.classifier.classifier import classifier, PageType

def test_classify_login(sample_ui_elements):
    context = {"ui": sample_ui_elements}
    result = classifier.classify(context)
    
    assert result["page_type"] == PageType.LOGIN
    assert result["scores"][PageType.LOGIN] > 0

def test_classify_search():
    context = {
        "ui": [
            {"tag": "input", "text": "", "id": "q", "placeholder": "search for products...", "type": "search"},
            {"tag": "button", "text": "Search", "id": "search-btn"}
        ]
    }
    result = classifier.classify(context)
    assert result["page_type"] == PageType.SEARCH

def test_classify_unknown():
    context = {
        "ui": [
            {"tag": "div", "text": "some random block"}
        ]
    }
    result = classifier.classify(context)
    assert result["page_type"] == PageType.UNKNOWN
