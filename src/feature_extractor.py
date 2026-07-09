"""
Feature extractor wrapper for the machine learning classifier.
Exposes the FeatureExtractor class from the browser_optimizer package.
"""

from browser_optimizer.classifier.feature_extractor import FeatureExtractor, FEATURE_COLUMNS

# Explicitly export for project structure requirements
__all__ = ["FeatureExtractor", "FEATURE_COLUMNS"]
