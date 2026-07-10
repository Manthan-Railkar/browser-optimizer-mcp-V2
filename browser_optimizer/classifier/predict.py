"""
Inference module for the Machine Learning Page Classifier.
Loads the trained LightGBM model and handles predictions with a confidence threshold.
"""

import os
import joblib
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Tuple
from browser_optimizer.utils.logger import logger
from browser_optimizer.classifier.feature_extractor import FeatureExtractor, FEATURE_COLUMNS
from browser_optimizer.config.settings import settings


class PageClassifierPredictor:
    """
    Handles loading trained model artifacts and running inference on page contexts.
    """

    _model = None
    _label_encoder = None
    _feature_names = None
    _loaded = False

    @classmethod
    def load_assets(cls):
        """
        Lazily load the classifier model, label encoder, and feature names.
        """
        if cls._loaded:
            return

        # Locate models folder relative to this package, or root
        possible_dirs = [
            # Package path
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "page-classifier", "models")),
            # Alternative package path (if directory structure is nested)
            os.path.abspath(os.path.join(os.path.dirname(__file__), "models")),
            # Root project path
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "models")),
        ]

        models_dir = None
        for d in possible_dirs:
            if os.path.exists(os.path.join(d, "page_classifier.pkl")):
                models_dir = d
                break

        if not models_dir:
            raise FileNotFoundError(
                f"Could not locate page_classifier.pkl in any of: {possible_dirs}"
            )

        logger.info(f"Loading page classifier models from: {models_dir}")
        try:
            cls._model = joblib.load(os.path.join(models_dir, "page_classifier.pkl"))
            cls._label_encoder = joblib.load(os.path.join(models_dir, "label_encoder.pkl"))
            cls._feature_names = joblib.load(os.path.join(models_dir, "feature_names.pkl"))
            cls._loaded = True
            logger.info("Page classifier assets loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load page classifier assets: {e}")
            raise

    def __init__(self):
        self.feature_extractor = FeatureExtractor()
        self.load_assets()

    def predict(self, context: Dict[str, Any], threshold: Optional[float] = None) -> Tuple[str, float, Dict[str, float]]:
        """
        Predict the page category along with confidence score and probabilities.
        
        Args:
            context (Dict[str, Any]): Webpage context containing ui, ax_tree, title, text_content, etc.
            threshold (float, optional): Classification confidence threshold. Defaults to CLASSIFICATION_THRESHOLD.
            
        Returns:
            Tuple[str, float, Dict[str, float]]: (predicted_page_type, confidence_score, all_class_probabilities)
        """
        if threshold is None:
            # Safely fetch setting, fall back to 0.65 if not defined on settings yet
            val = getattr(settings, "CLASSIFICATION_THRESHOLD", 0.65)
            threshold = float(val) if val is not None else 0.65

        if self._model is None or self._label_encoder is None or self._feature_names is None:
            raise RuntimeError("Page classifier assets are not loaded. Call load_assets() first.")

        # 1. Extract raw numerical features
        features = self.feature_extractor.extract_features(context)

        # 2. Format features as a pandas DataFrame and align column order
        df_features = pd.DataFrame([features])
        # Reorder columns based on training features list
        df_features = df_features[self._feature_names]

        # 3. Predict class probabilities
        try:
            probs = self._model.predict_proba(df_features)[0]
        except Exception as e:
            logger.error(f"Inference failed: {e}")
            # Safe fallback in case of prediction failure
            fallback = [0.0] * len(self._label_encoder.classes_)
            fallback[list(self._label_encoder.classes_).index("UNKNOWN")] = 1.0
            probs = np.array(fallback)

        # Map classes to their probabilities
        classes = self._label_encoder.classes_
        class_probs = {str(classes[i]).lower(): float(probs[i]) for i in range(len(classes))}

        # Get highest probability prediction
        best_idx = int(probs.argmax())
        best_class = str(classes[best_idx]).lower()  # Normalize to lowercase
        best_prob = float(probs[best_idx])

        logger.debug(f"Predicted class: {best_class} with confidence {best_prob:.4f}")

        # 4. Confidence Threshold Fallback
        if best_prob < threshold:
            logger.info(
                f"Prediction confidence {best_prob:.4f} is below threshold {threshold:.2f}. "
                f"Falling back to 'unknown'."
            )
            return "unknown", best_prob, class_probs

        return best_class, best_prob, class_probs
