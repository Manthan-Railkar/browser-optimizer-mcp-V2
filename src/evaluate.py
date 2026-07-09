"""
Independent evaluation module for the Machine Learning Page Classifier.
Loads the trained model and artifacts, evaluates performance on the test set,
and generates metrics and visualization plots for feature importance and confusion matrices.
"""

import os
import joblib
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

from browser_optimizer.utils.logger import logger
from browser_optimizer.classifier.feature_extractor import FEATURE_COLUMNS


def run_evaluation(visualize: bool = True):
    """
    Load saved model, reconstruct the split test set, evaluate, and save plots.
    """
    logger.info("Starting independent model evaluation...")

    # 1. Resolve models directory
    possible_dirs = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "browser_optimizer", "page-classifier", "models")),
        "models"
    ]
    
    models_dir = None
    for d in possible_dirs:
        if os.path.exists(os.path.join(d, "page_classifier.pkl")):
            models_dir = d
            break

    if not models_dir:
        raise FileNotFoundError(f"Could not locate page_classifier.pkl in any of: {possible_dirs}")

    logger.info(f"Loading models from: {models_dir}")
    model = joblib.load(os.path.join(models_dir, "page_classifier.pkl"))
    label_encoder = joblib.load(os.path.join(models_dir, "label_encoder.pkl"))
    feature_names = joblib.load(os.path.join(models_dir, "feature_names.pkl"))

    # 2. Locate dataset and recreate the exact split
    dataset_paths = [
        os.path.join("data", "page_dataset.csv"),
        os.path.join("browser_optimizer", "page-classifier", "data", "page_dataset.csv"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "page_dataset.csv")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "browser_optimizer", "page-classifier", "data", "page_dataset.csv"))
    ]

    dataset_path = None
    for path in dataset_paths:
        if os.path.exists(path):
            dataset_path = path
            break

    if not dataset_path:
        raise FileNotFoundError(f"Could not find page_dataset.csv in: {dataset_paths}")

    df = pd.read_csv(dataset_path)
    X = df[FEATURE_COLUMNS]
    y_encoded = label_encoder.transform(df["page_type"])

    # Split using same random state as training (42) to evaluate on the unseen test set
    _, X_test, _, y_test = train_test_split(
        X, y_encoded, test_size=0.2, stratify=y_encoded, random_state=42
    )

    # 3. Align features
    X_test = X_test[feature_names]

    # 4. Predict
    logger.info("Running inference on test dataset...")
    y_pred = model.predict(X_test)
    y_pred_proba = model.predict_proba(X_test)

    # Calculate metrics
    accuracy = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, target_names=label_encoder.classes_)
    conf_matrix = confusion_matrix(y_test, y_pred)

    print("\n=======================================================")
    print("              CLASSIFICATION METRICS REPORT            ")
    print("=======================================================")
    print(f"Overall Accuracy: {accuracy:.6%}\n")
    print("Classification Report:")
    print(report)
    print("Confusion Matrix:")
    print(conf_matrix)
    print("=======================================================\n")

    # 5. Visualizations
    if visualize:
        logger.info("Generating evaluation plots...")
        plots_dir = os.path.join(models_dir, "plots")
        os.makedirs(plots_dir, exist_ok=True)

        # Plot 1: Confusion Matrix
        plt.figure(figsize=(10, 8))
        sns.heatmap(
            conf_matrix,
            annot=True,
            fmt="d",
            cmap="Blues",
            xticklabels=label_encoder.classes_,
            yticklabels=label_encoder.classes_
        )
        plt.title("Confusion Matrix - Webpage Classifier (LightGBM)")
        plt.ylabel("True Class")
        plt.xlabel("Predicted Class")
        plt.tight_layout()
        cm_path = os.path.join(plots_dir, "confusion_matrix.png")
        plt.savefig(cm_path, dpi=150)
        plt.close()
        logger.info(f"Saved confusion matrix plot to: {cm_path}")

        # Plot 2: Feature Importance
        importances = model.feature_importances_
        indices = np.argsort(importances)[::-1]
        sorted_features = [feature_names[i] for i in indices]
        sorted_importances = importances[indices]

        plt.figure(figsize=(12, 8))
        sns.barplot(
            x=sorted_importances[:20],
            y=sorted_features[:20],
            palette="viridis"
        )
        plt.title("Top 20 Feature Importances (LightGBM)")
        plt.xlabel("Importance (Split/Gain count)")
        plt.ylabel("Feature")
        plt.tight_layout()
        fi_path = os.path.join(plots_dir, "feature_importance.png")
        plt.savefig(fi_path, dpi=150)
        plt.close()
        logger.info(f"Saved feature importance plot to: {fi_path}")


if __name__ == "__main__":
    # Allow command line to toggle visualization
    import sys
    vis = "--no-plots" not in sys.argv
    run_evaluation(visualize=vis)
