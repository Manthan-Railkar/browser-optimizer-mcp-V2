from enum import Enum
from collections import Counter
from typing import Dict, List, Any


class PageType(str, Enum):
    LOGIN = "login"
    SEARCH = "search"
    SURVEY = "survey"
    CHECKOUT = "checkout"
    PRODUCT = "product"
    DASHBOARD = "dashboard"
    UNKNOWN = "unknown"


class TaskClassifier:
    """
    Rule-based page classifier.

    Input:
        {
            "ui": [
                {
                    "tag": "...",
                    "text": "...",
                    "placeholder": "...",
                    "type": "...",
                    "id": "...",
                    "name": "..."
                }
            ]
        }

    Output:
        {
            "page_type": PageType.LOGIN,
            "scores": {...}
        }
    """

    def classify(self, context: Dict[str, Any]) -> Dict[str, Any]:

        ui = context.get("ui", [])

        scores = Counter({
            PageType.LOGIN: 0,
            PageType.SEARCH: 0,
            PageType.SURVEY: 0,
            PageType.CHECKOUT: 0,
            PageType.PRODUCT: 0,
            PageType.DASHBOARD: 0
        })

        for element in ui:

            self._score_login(element, scores)
            self._score_search(element, scores)
            self._score_checkout(element, scores)
            self._score_product(element, scores)
            self._score_survey(element, scores)
            self._score_dashboard(element, scores)

        best = max(scores, key=scores.get)

        if scores[best] == 0:
            best = PageType.UNKNOWN

        return {
            "page_type": best,
            "scores": dict(scores)
        }

    # --------------------------------------------------------
    # LOGIN
    # --------------------------------------------------------

    def _score_login(self, element, scores):

        text = self._text(element)
        placeholder = self._placeholder(element)
        input_type = self._input_type(element)

        if input_type == "password":
            scores[PageType.LOGIN] += 40

        if "email" in placeholder:
            scores[PageType.LOGIN] += 20

        if "username" in placeholder:
            scores[PageType.LOGIN] += 20

        if "login" in text:
            scores[PageType.LOGIN] += 20

        if "log in" in text:
            scores[PageType.LOGIN] += 20

        if "sign in" in text:
            scores[PageType.LOGIN] += 20

        if "forgot password" in text:
            scores[PageType.LOGIN] += 10

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    def _score_search(self, element, scores):

        text = self._text(element)
        placeholder = self._placeholder(element)
        input_type = self._input_type(element)

        if input_type == "search":
            scores[PageType.SEARCH] += 30

        if "search" in placeholder:
            scores[PageType.SEARCH] += 20

        if "search" in text:
            scores[PageType.SEARCH] += 20

    # --------------------------------------------------------
    # CHECKOUT
    # --------------------------------------------------------

    def _score_checkout(self, element, scores):

        text = self._text(element)

        keywords = [
            "checkout",
            "payment",
            "shipping",
            "billing",
            "address",
            "place order",
            "credit card",
            "upi",
            "debit card"
        ]

        for keyword in keywords:
            if keyword in text:
                scores[PageType.CHECKOUT] += 15

    # --------------------------------------------------------
    # PRODUCT
    # --------------------------------------------------------

    def _score_product(self, element, scores):

        text = self._text(element)

        if "add to cart" in text:
            scores[PageType.PRODUCT] += 30

        if "buy now" in text:
            scores[PageType.PRODUCT] += 30

        if "price" in text:
            scores[PageType.PRODUCT] += 10

        if "rating" in text:
            scores[PageType.PRODUCT] += 10

        if "wishlist" in text:
            scores[PageType.PRODUCT] += 10

    # --------------------------------------------------------
    # SURVEY
    # --------------------------------------------------------

    def _score_survey(self, element, scores):

        text = self._text(element)

        keywords = [
            "question",
            "submit",
            "next",
            "previous",
            "option",
            "survey",
            "response"
        ]

        for keyword in keywords:
            if keyword in text:
                scores[PageType.SURVEY] += 10

    # --------------------------------------------------------
    # DASHBOARD
    # --------------------------------------------------------

    def _score_dashboard(self, element, scores):

        text = self._text(element)

        keywords = [
            "dashboard",
            "analytics",
            "reports",
            "statistics",
            "users",
            "settings",
            "overview",
            "metrics"
        ]

        for keyword in keywords:
            if keyword in text:
                scores[PageType.DASHBOARD] += 15

    # --------------------------------------------------------
    # Utility Functions
    # --------------------------------------------------------

    @staticmethod
    def _text(element):

        return (element.get("text") or "").lower()

    @staticmethod
    def _placeholder(element):

        return (element.get("placeholder") or "").lower()

    @staticmethod
    def _input_type(element):

        return (element.get("type") or "").lower()


classifier = TaskClassifier()