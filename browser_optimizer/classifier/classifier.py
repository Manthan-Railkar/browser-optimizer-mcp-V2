from enum import Enum
from typing import Dict, List, Any, Optional
from browser_optimizer.utils.logger import logger
from browser_optimizer.classifier.predict import PageClassifierPredictor


class PageType(str, Enum):
    HOME = "home"
    LOGIN = "login"
    REGISTER = "register"
    SEARCH = "search"
    PRODUCT = "product"
    CART = "cart"
    CHECKOUT = "checkout"
    PAYMENT = "payment"
    PROFILE = "profile"
    SETTINGS = "settings"
    ERROR = "error"
    UNKNOWN = "unknown"
    SURVEY = "survey"
    DASHBOARD = "dashboard"


class TaskClassifier:
    """
    LightGBM-based Machine Learning page classifier.
    Acts as a plug-and-play replacement for the heuristics-based TaskClassifier.
    """

    def __init__(self):
        """
        Initializes the Page Classifier by loading the predictor.
        """
        self._predictor: Optional[PageClassifierPredictor] = None
        try:
            self._predictor = PageClassifierPredictor()
            logger.info("ML TaskClassifier initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize ML PageClassifierPredictor: {e}")
            self._predictor = None

    def classify(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classifies the page type based on the provided context dictionary.
        
        Args:
            context (Dict[str, Any]): Webpage context dictionary.
            
        Returns:
            Dict[str, Any]: Dict containing predicted 'page_type' and class 'scores'.
        """
        if not self._predictor:
            logger.warning("Predictor not loaded. Falling back to heuristic classifier.")
            return self._classify_heuristics(context)

        try:
            best_class, best_prob, class_probs = self._predictor.predict(context)
            
            # Map predictions to PageType enum values.
            try:
                page_type = PageType(best_class)
            except ValueError:
                page_type = PageType.UNKNOWN

            # Check if prediction fell back to "unknown" due to low confidence threshold
            if page_type == PageType.UNKNOWN or best_class == "unknown":
                logger.info("ML classification confidence below threshold or unknown. Invoking heuristic fallback classifier...")
                heuristic_result = self._classify_heuristics(context)
                if heuristic_result["page_type"] != PageType.UNKNOWN:
                    logger.info(f"Heuristic fallback classifier matched category: {heuristic_result['page_type']}")
                    h_scores = {PageType(k): float(v) for k, v in heuristic_result["scores"].items()}
                    sum_scores = sum(h_scores.values())
                    if sum_scores > 0:
                        norm_scores = {k: v / sum_scores for k, v in h_scores.items()}
                    else:
                        norm_scores = {}
                    # Ensure we set a reasonable high probability for the predicted category
                    norm_scores[heuristic_result["page_type"]] = 0.8
                    norm_scores[PageType.UNKNOWN] = 0.2
                    return {
                        "page_type": heuristic_result["page_type"],
                        "scores": norm_scores
                    }

            # Build scores dict mapped to PageType enum values
            scores = {}
            for name, prob in class_probs.items():
                try:
                    p_type = PageType(name)
                    scores[p_type] = prob
                except ValueError:
                    # Ignore classes that are not mapped in PageType enum
                    pass

            return {
                "page_type": page_type,
                "scores": scores
            }

        except Exception as e:
            logger.error(f"Inference error during classify: {e}")
            logger.info("Falling back to heuristic classifier due to error.")
            try:
                return self._classify_heuristics(context)
            except Exception as he:
                logger.error(f"Heuristic classifier also failed: {he}")
                return {
                    "page_type": PageType.UNKNOWN,
                    "scores": {PageType.UNKNOWN: 1.0}
                }

    def _classify_heuristics(self, context: Dict[str, Any]) -> Dict[str, Any]:
        from collections import Counter
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

        best = max(scores, key=lambda k: scores[k])

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


# Singleton instance exported for use by main server pipeline and scripts
classifier = TaskClassifier()