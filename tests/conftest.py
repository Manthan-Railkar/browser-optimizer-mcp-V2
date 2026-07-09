import pytest
from typing import Dict, Any, List

@pytest.fixture
def sample_login_html() -> str:
    return """
    <html>
        <head>
            <style>body { font-family: sans-serif; }</style>
            <script>console.log("hello");</script>
        </head>
        <body>
            <header>
                <h1>Welcome to My App</h1>
            </header>
            <form id="login-form">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" placeholder="Enter username" />
                
                <label for="password">Password</label>
                <input type="password" id="password" name="password" placeholder="Password" />
                
                <button type="submit" id="submit-btn">Log In</button>
                <a href="/forgot">forgot password?</a>
            </form>
            <footer>
                <p>Copyright 2026</p>
            </footer>
        </body>
    </html>
    """

@pytest.fixture
def sample_search_html() -> str:
    return """
    <html>
        <body>
            <div class="search-container">
                <input type="search" id="query" placeholder="search products..." />
                <button id="search-btn">Search</button>
            </div>
            <div class="results">
                <p>No results found</p>
            </div>
        </body>
    </html>
    """

@pytest.fixture
def sample_ui_elements() -> List[Dict[str, Any]]:
    return [
        {"tag": "input", "text": "", "id": "username", "name": "username", "placeholder": "Enter username", "type": "text"},
        {"tag": "input", "text": "", "id": "password", "name": "password", "placeholder": "Password", "type": "password"},
        {"tag": "button", "text": "Log In", "id": "submit-btn", "name": None, "placeholder": None, "type": "submit"},
        {"tag": "a", "text": "forgot password?", "id": None, "name": None, "placeholder": None, "type": None}
    ]
