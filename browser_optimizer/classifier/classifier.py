from enum import Enum
from typing import Dict, List, Any
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
            logger.warning("Predictor not loaded. Falling back to UNKNOWN.")
            return {
                "page_type": PageType.UNKNOWN,
                "scores": {PageType.UNKNOWN: 1.0}
            }

        try:
            best_class, best_prob, class_probs = self._predictor.predict(context)
            
            # Map predictions to PageType enum values.
            try:
                page_type = PageType(best_class)
            except ValueError:
                page_type = PageType.UNKNOWN

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
            return {
                "page_type": PageType.UNKNOWN,
                "scores": {PageType.UNKNOWN: 1.0}
            }


# Singleton instance exported for use by main server pipeline and scripts
classifier = TaskClassifier()