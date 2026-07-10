"""
Training script for the Machine Learning Page Classifier.
Loads the dataset, trains a multiclass LightGBM classifier, evaluates its performance,
and saves the trained model, label encoder, and feature names.
"""

import os
import joblib
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
import lightgbm as lgb

from browser_optimizer.utils.logger import logger
from browser_optimizer.classifier.feature_extractor import FeatureExtractor, FEATURE_COLUMNS


def train_classifier():
    """
    Load dataset, train the LightGBM model, evaluate, and save artifacts.
    """
    logger.info("Starting Machine Learning Page Classifier training pipeline...")

    # 1. Locate dataset
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
        raise FileNotFoundError(f"Could not locate page_dataset.csv in any of: {dataset_paths}")

    logger.info(f"Loading training dataset from: {dataset_path}")
    df = pd.read_csv(dataset_path)

    # Inspect and validate dataset
    logger.info(f"Dataset shape: {df.shape}")
    missing_values = df.isnull().sum().sum()
    logger.info(f"Total missing values: {missing_values}")
    if missing_values > 0:
        logger.warning("Dataset contains missing values! Filling them with median values.")
        df = df.fillna(df.median(numeric_only=True))

    class_distribution = df["page_type"].value_counts()
    logger.info("Class distribution in dataset:")
    for label, count in class_distribution.items():
        logger.info(f"  {label}: {count}")

    # Validate feature list matches expectations
    missing_cols = [col for col in FEATURE_COLUMNS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Required features missing from CSV: {missing_cols}")

    # 2. Separate features and label
    X = df[FEATURE_COLUMNS]
    y = df["page_type"]

    # 3. Encode labels using LabelEncoder
    logger.info("Encoding labels...")
    label_encoder = LabelEncoder()
    y_encoded = label_encoder.fit_transform(y)
    
    # 4. Resolve output models folder
    possible_output_dirs = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "browser_optimizer", "page-classifier", "models")),
        "models"
    ]
    
    output_dir = None
    for d in possible_output_dirs:
        # Create directory if it is a reasonable target path
        try:
            os.makedirs(d, exist_ok=True)
            output_dir = d
            break
        except Exception:
            continue

    if not output_dir:
        output_dir = "models"
        os.makedirs(output_dir, exist_ok=True)

    logger.info(f"Saving encoder and feature names to: {output_dir}")
    joblib.dump(label_encoder, os.path.join(output_dir, "label_encoder.pkl"))
    joblib.dump(FEATURE_COLUMNS, os.path.join(output_dir, "feature_names.pkl"))

    # Also save to the package directory to keep them synced
    package_models_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "browser_optimizer", "page-classifier", "models"))
    if os.path.exists(os.path.dirname(package_models_dir)):
        os.makedirs(package_models_dir, exist_ok=True)
        logger.info(f"Syncing artifacts to package directory: {package_models_dir}")
        joblib.dump(label_encoder, os.path.join(package_models_dir, "label_encoder.pkl"))
        joblib.dump(FEATURE_COLUMNS, os.path.join(package_models_dir, "feature_names.pkl"))

    # 5. Stratified 80/20 split
    logger.info("Performing 80/20 stratified train-test split...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_encoded, test_size=0.2, stratify=y_encoded, random_state=42
    )

    # 6. Initialize & Train LightGBM classifier
    logger.info("Initializing LightGBM Multiclass Classifier...")
    classifier = lgb.LGBMClassifier(
        objective="multiclass",
        num_class=12,
        learning_rate=0.05,
        n_estimators=300,
        max_depth=8,
        num_leaves=31,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbose=-1
    )

    logger.info("Training the model...")
    classifier.fit(
        X_train,
        y_train,
        eval_set=[(X_test, y_test)],
        callbacks=[lgb.early_stopping(stopping_rounds=30, verbose=False)]
    )

    # 7. Evaluate
    logger.info("Evaluating trained model...")
    y_pred = classifier.predict(X_test)
    y_pred_proba = classifier.predict_proba(X_test)

    # Accuracy, Precision, Recall, F1
    accuracy = accuracy_score(y_test, y_pred)
    logger.info(f"Model Accuracy on Test Set: {accuracy:.4f}")
    
    report = classification_report(
        y_test, y_pred, target_names=label_encoder.classes_
    )
    logger.info(f"Classification Report:\n{report}")

    # Confusion matrix
    conf_matrix = confusion_matrix(y_test, y_pred)
    logger.info(f"Confusion Matrix:\n{conf_matrix}")

    # Feature Importance
    importances = classifier.feature_importances_
    importance_df = pd.DataFrame({
        "Feature": FEATURE_COLUMNS,
        "Importance": importances
    }).sort_values(by="Importance", ascending=False)
    
    logger.info("Top 10 Most Important Features:")
    for idx, row in importance_df.head(10).iterrows():
        logger.info(f"  {row['Feature']}: {row['Importance']}")

    # Prediction Confidence (mean confidence for correct and incorrect predictions)
    correct_mask = (y_test == y_pred)
    correct_confidences = y_pred_proba[np.arange(len(y_test)), y_pred][correct_mask]
    incorrect_confidences = y_pred_proba[np.arange(len(y_test)), y_pred][~correct_mask]

    logger.info(f"Mean confidence for CORRECT predictions: {correct_confidences.mean():.4f}")
    if len(incorrect_confidences) > 0:
        logger.info(f"Mean confidence for INCORRECT predictions: {incorrect_confidences.mean():.4f}")

    # 8. Save model
    model_save_path = os.path.join(output_dir, "page_classifier.pkl")
    logger.info(f"Saving trained LightGBM model to: {model_save_path}")
    joblib.dump(classifier, model_save_path)

    # Sync to package
    if os.path.exists(package_models_dir):
        pkg_save_path = os.path.join(package_models_dir, "page_classifier.pkl")
        logger.info(f"Syncing model to package directory: {pkg_save_path}")
        joblib.dump(classifier, pkg_save_path)

    logger.info("Classifier training pipeline completed successfully.")


if __name__ == "__main__":
    train_classifier()
