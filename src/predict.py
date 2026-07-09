"""
Prediction pipeline wrapper for the machine learning classifier.
Exposes the PageClassifierPredictor class and provides a CLI for running manual predictions.
"""

import sys
import json
from typing import Dict, Any
from browser_optimizer.classifier.predict import PageClassifierPredictor


def main():
    """
    CLI runner for predict.py to manually inspect a prediction on a JSON file or string.
    """
    if len(sys.argv) < 2:
        print("Usage: python predict.py <json_context_file_or_string>")
        sys.exit(1)

    input_arg = sys.argv[1]
    try:
        # Check if argument is a file path
        import os
        if os.path.exists(input_arg):
            with open(input_arg, "r", encoding="utf-8") as f:
                context = json.load(f)
        else:
            context = json.loads(input_arg)
    except Exception as e:
        print(f"Error parsing input context: {e}")
        sys.exit(1)

    print("Initializing predictor...")
    predictor = PageClassifierPredictor()
    
    print("Running prediction...")
    best_class, confidence, class_probs = predictor.predict(context)
    
    print("\n=== Prediction Result ===")
    print(f"Predicted Class: {best_class.upper()}")
    print(f"Confidence:      {confidence:.4f}")
    print("\n--- Class Probabilities ---")
    for cls, prob in sorted(class_probs.items(), key=lambda x: x[1], reverse=True):
        print(f"  {cls:12s}: {prob:.4f}")


if __name__ == "__main__":
    main()
