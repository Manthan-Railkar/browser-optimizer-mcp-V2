from browser_optimizer.classifier.classifier import classifier, PageType


def test_classify_login(sample_ui_elements):
    # Mock realistic page layout features alongside elements
    context = {
        "ui": sample_ui_elements,
        "heading_count": 3,
        "image_count": 4,
        "link_count": 6,
        "visible_text_length": 200,
        "title_length": 30,
        "title": "Login - Sign In to Your Account",
        "text_content": "Please log in or sign in to access your secure dashboard profile. If you forgot password, retrieve it. If you need support, contact us."
    }
    result = classifier.classify(context)
    
    assert result["page_type"] == PageType.LOGIN
    assert result["scores"][PageType.LOGIN] > 0.65


def test_classify_search():
    # Mock realistic search page features alongside elements
    context = {
        "ui": [
            {"tag": "input", "text": "", "id": "q", "placeholder": "search for products...", "type": "search"},
            {"tag": "button", "text": "Search", "id": "search-btn"}
        ],
        "heading_count": 2,
        "image_count": 5,
        "link_count": 12,
        "visible_text_length": 180,
        "title_length": 20,
        "title": "Search Catalog",
        "text_content": "Use the search box below to query and find items in our online shop catalog. Search results will be shown here."
    }
    result = classifier.classify(context)
    assert result["page_type"] == PageType.SEARCH
    assert result["scores"][PageType.SEARCH] > 0.65


def test_classify_unknown():
    # Mock a standard page with generic content (no login/search/checkout keywords)
    # This will have lower confidence, triggering the threshold fallback to PageType.UNKNOWN
    context = {
        "ui": [
            {"tag": "a", "text": "About Us", "id": "about-link"},
            {"tag": "a", "text": "Contact Us", "id": "contact-link"}
        ],
        "heading_count": 5,
        "image_count": 10,
        "link_count": 20,
        "visible_text_length": 500,
        "title_length": 35,
        "title": "About Our Company and Mission",
        "text_content": "Welcome to our corporate homepage. We are dedicated to providing excellent service and support to our clients. Read about our team, our mission, values, history, and current job openings."
    }
    result = classifier.classify(context)
    assert result["page_type"] == PageType.UNKNOWN
    assert result["scores"][PageType.UNKNOWN] > 0
