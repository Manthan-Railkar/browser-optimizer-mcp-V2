"""
Unit tests for the structural embedding module.
Verifies embedding generation, cosine similarity, and near-duplicate detection.
"""

import pytest
from browser_optimizer.cache.embedding import StructuralEmbedding, EMBEDDING_DIM


@pytest.fixture
def embedder():
    return StructuralEmbedding()


# ─── Sample HTML fixtures ──────────────────────────────────

LOGIN_PAGE_A = """
<html>
<head><title>Login</title></head>
<body>
  <div class="container auth-wrapper">
    <form id="login-form" class="auth-form">
      <label for="email">Email</label>
      <input type="email" id="email" name="email" placeholder="Enter email" />
      <label for="password">Password</label>
      <input type="password" id="password" name="password" placeholder="Password" />
      <button type="submit" id="login-btn">Log In</button>
      <a href="/forgot">Forgot password?</a>
    </form>
  </div>
</body>
</html>
"""

# Same template as LOGIN_PAGE_A, but different text content and element values
LOGIN_PAGE_B = """
<html>
<head><title>Sign In to Dashboard</title></head>
<body>
  <div class="container auth-wrapper">
    <form id="login-form" class="auth-form">
      <label for="email">Your Email Address</label>
      <input type="email" id="email" name="email" placeholder="you@company.com" />
      <label for="password">Secret Key</label>
      <input type="password" id="password" name="password" placeholder="Enter password" />
      <button type="submit" id="login-btn">Sign In</button>
      <a href="/reset">Reset password?</a>
    </form>
  </div>
</body>
</html>
"""

PRODUCT_PAGE = """
<html>
<head><title>Product - Widget Pro</title></head>
<body>
  <div class="product-container">
    <img src="/img/widget.jpg" id="product-img" />
    <h1>Widget Pro</h1>
    <span class="price">$49.99</span>
    <p class="description">The best widget money can buy.</p>
    <div class="actions">
      <button id="add-to-cart">Add to Cart</button>
      <button id="buy-now">Buy Now</button>
      <select id="quantity" name="quantity">
        <option value="1">1</option>
        <option value="2">2</option>
        <option value="3">3</option>
      </select>
    </div>
    <div class="reviews">
      <ul>
        <li>Great product! ★★★★★</li>
        <li>Good value. ★★★★</li>
      </ul>
    </div>
  </div>
</body>
</html>
"""

EMPTY_PAGE = "<html><body></body></html>"


# ─── Tests ─────────────────────────────────────────────────

class TestEmbeddingGeneration:
    """Tests for StructuralEmbedding.generate()."""

    def test_embedding_has_correct_dimension(self, embedder):
        """Generated embedding should have exactly EMBEDDING_DIM floats."""
        emb = embedder.generate(LOGIN_PAGE_A)
        assert len(emb) == EMBEDDING_DIM

    def test_identical_html_produces_identical_embedding(self, embedder):
        """The same HTML should always produce the exact same embedding."""
        emb1 = embedder.generate(LOGIN_PAGE_A)
        emb2 = embedder.generate(LOGIN_PAGE_A)
        assert emb1 == emb2

    def test_empty_page_produces_valid_embedding(self, embedder):
        """An almost-empty page should still return a valid vector."""
        emb = embedder.generate(EMPTY_PAGE)
        assert len(emb) == EMBEDDING_DIM
        # At least some values should be non-zero (html + body tags exist)
        assert any(v != 0.0 for v in emb)

    def test_completely_empty_html(self, embedder):
        """Fully empty string should return a zero vector without crashing."""
        emb = embedder.generate("")
        assert len(emb) == EMBEDDING_DIM


class TestCosineSimilarity:
    """Tests for StructuralEmbedding.cosine_similarity()."""

    def test_identical_vectors_return_one(self, embedder):
        a = [1.0, 2.0, 3.0]
        assert abs(embedder.cosine_similarity(a, a) - 1.0) < 1e-9

    def test_orthogonal_vectors_return_zero(self, embedder):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert abs(embedder.cosine_similarity(a, b)) < 1e-9

    def test_zero_vector_returns_zero(self, embedder):
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert embedder.cosine_similarity(a, b) == 0.0

    def test_proportional_vectors_return_one(self, embedder):
        """Vectors that are scalar multiples should have similarity = 1.0."""
        a = [1.0, 2.0, 3.0]
        b = [2.0, 4.0, 6.0]
        assert abs(embedder.cosine_similarity(a, b) - 1.0) < 1e-9


class TestSemanticSimilarity:
    """Integration tests: structurally similar pages should have high similarity."""

    def test_same_template_different_text_is_highly_similar(self, embedder):
        """
        Two login pages with the same DOM structure but different labels/placeholders
        should produce similarity >= 0.95.
        """
        emb_a = embedder.generate(LOGIN_PAGE_A)
        emb_b = embedder.generate(LOGIN_PAGE_B)
        sim = embedder.cosine_similarity(emb_a, emb_b)
        assert sim >= 0.95, f"Expected >= 0.95, got {sim:.4f}"

    def test_different_page_types_have_low_similarity(self, embedder):
        """
        A login page and a product page should have low similarity (< 0.8).
        """
        emb_login = embedder.generate(LOGIN_PAGE_A)
        emb_product = embedder.generate(PRODUCT_PAGE)
        sim = embedder.cosine_similarity(emb_login, emb_product)
        assert sim < 0.8, f"Expected < 0.8, got {sim:.4f}"

    def test_empty_vs_real_page_has_low_similarity(self, embedder):
        """Empty page vs a real page should have very low similarity."""
        emb_empty = embedder.generate(EMPTY_PAGE)
        emb_login = embedder.generate(LOGIN_PAGE_A)
        sim = embedder.cosine_similarity(emb_empty, emb_login)
        assert sim < 0.5, f"Expected < 0.5, got {sim:.4f}"
