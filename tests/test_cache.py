import time
from app.cache.cache import SemanticCache

def test_cache_hit_and_miss():
    cache = SemanticCache()
    url = "https://example.com/login"
    html_content = "<html><body><button>Login</button></body></html>"
    context = {"ui": [{"tag": "button", "text": "Login"}]}
    
    # Verify lookup returns None on miss
    assert cache.lookup(url, html_content) is None
    
    # Store entry
    cache.store(url, html_content, context)
    
    # Lookup should now hit
    retrieved = cache.lookup(url, html_content)
    assert retrieved is not None
    assert retrieved["ui"][0]["text"] == "Login"
    
    # If HTML content changes, it should miss
    changed_html = "<html><body><button>Sign In</button></body></html>"
    assert cache.lookup(url, changed_html) is None
    
    # Cache clear test
    cache.store(url, html_content, context)
    cache.clear()
    assert cache.lookup(url, html_content) is None

def test_cache_ttl_expiry():
    # Set cache with short TTL (e.g. 1 second)
    cache = SemanticCache(ttl=1)
    
    url = "https://example.com/temp"
    html = "<div>temp</div>"
    context = {"val": "123"}
    
    cache.store(url, html, context)
    assert cache.lookup(url, html) is not None
    
    # Wait for TTL to expire
    time.sleep(1.1)
    
    # Lookup should now miss
    assert cache.lookup(url, html) is None
