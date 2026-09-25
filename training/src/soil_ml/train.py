from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from soil_ml import REQUIRED_SENSOR_FEATURES, MODEL_FEATURES
from soil_ml.fusion import fuse_frame
from soil_ml.tiny_forest import TinyRandomForest


def load_training_data(csv_path: str | Path) -> tuple[pd.DataFrame, pd.Series]:
    df = pd.read_csv(csv_path)
    missing = [feature for feature in REQUIRED_SENSOR_FEATURES + ["label"] if feature not in df.columns]
    if missing:
        raise ValueError(f"Training data is missing required columns: {missing}")
    x = df[REQUIRED_SENSOR_FEATURES].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(x.to_numpy()).all() or df["label"].isna().any():
        raise ValueError("Missing or nonfinite training values are not permitted")
    if df.duplicated().any():
        raise ValueError("Duplicate rows must be resolved before splitting")
    if df["label"].value_counts().min() < 10:
        raise ValueError("At least 10 rows per class are required")
    return x.copy(), df["label"].astype(str).copy()


def stratified_split(
    x: pd.DataFrame,
    y: pd.Series,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    rng = np.random.default_rng(seed)
    train_indices: list[int] = []
    val_indices: list[int] = []
    test_indices: list[int] = []
    groups = list(y.groupby(y))
    sizes = np.array([len(group) for _, group in groups])
    def allocate(fraction):
        raw = sizes * fraction
        counts = np.floor(raw).astype(int)
        order = np.argsort(-(raw - counts), kind="stable")
        counts[order[:int(round(len(y) * fraction)) - int(counts.sum())]] += 1
        return counts
    train_counts, val_counts = allocate(0.70), allocate(0.15)
    for group_index, (_, group) in enumerate(groups):
        indices = group.index.to_numpy(copy=True)
        rng.shuffle(indices)
        train_end = train_counts[group_index]
        val_end = train_end + val_counts[group_index]
        train_indices.extend(indices[:train_end].tolist())
        val_indices.extend(indices[train_end:val_end].tolist())
        test_indices.extend(indices[val_end:].tolist())
    rng.shuffle(train_indices)
    rng.shuffle(val_indices)
    rng.shuffle(test_indices)
    return (
        x.loc[train_indices].reset_index(drop=True),
        x.loc[val_indices].reset_index(drop=True),
        x.loc[test_indices].reset_index(drop=True),
        y.loc[train_indices].reset_index(drop=True),
        y.loc[val_indices].reset_index(drop=True),
        y.loc[test_indices].reset_index(drop=True),
    )


def train_random_forest(x_train: pd.DataFrame, y_train: pd.Series) -> TinyRandomForest:
    """Fit the seeded TinyRandomForest used for ESP32 export.

    This custom implementation is a prototype fallback for unavailable local
    dependencies. Scikit-learn forests can also be exported to C/C++;
    pickle incompatibility does not prevent using scikit-learn for training.
    """
    return TinyRandomForest(
        n_estimators=15,
        max_depth=5,
        min_samples_leaf=2,
        random_state=42,
    ).fit(fuse_frame(x_train).to_numpy(dtype=float), y_train.tolist())


def evaluate_model(model: TinyRandomForest, x: pd.DataFrame, y: pd.Series) -> dict:
    predictions = model.predict(fuse_frame(x).to_numpy(dtype=float))
    predicted_series = pd.Series(predictions)
    labels = list(model.classes_)
    matrix = []
    per_label = {}
    for label in labels:
        row = []
        for predicted_label in labels:
            row.append(int(sum((y == label) & (predicted_series == predicted_label))))
        matrix.append(row)

    precisions = []
    recalls = []
    f1s = []
    for index, label in enumerate(labels):
        tp = matrix[index][index]
        fp = sum(matrix[row][index] for row in range(len(labels)) if row != index)
        fn = sum(matrix[index][col] for col in range(len(labels)) if col != index)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        support = int(sum(matrix[index]))
        precisions.append(precision)
        recalls.append(recall)
        f1s.append(f1)
        per_label[label] = {
            "precision": float(precision),
            "recall": float(recall),
            "f1-score": float(f1),
            "support": support,
        }

    correct = sum(int(actual == predicted) for actual, predicted in zip(y.tolist(), predictions))
    accuracy = correct / len(y) if len(y) else 0.0
    return {
        "accuracy": float(accuracy),
        "precision_macro": float(np.mean(precisions)),
        "recall_macro": float(np.mean(recalls)),
        "macro_f1": float(np.mean(f1s)),
        "classification_report": per_label,
        "confusion_matrix": matrix,
        "labels": labels,
    }


def model_size_summary(model: TinyRandomForest) -> dict:
    total_nodes = int(sum(len(tree) for tree in model.trees_))
    estimated_flash_bytes = int(total_nodes * (1 + 4 + 2 + 2 + 1) + len(model.trees_) * 2)
    return {
        "n_estimators": len(model.trees_),
        "max_depth": model.max_depth,
        "total_tree_nodes": total_nodes,
        "estimated_const_flash_bytes": estimated_flash_bytes,
        "esp32_decision": "fits_prototype_budget" if estimated_flash_bytes < 180_000 else "too_large_reduce_model",
        "note": "Arrays are exported as const data for flash. Runtime RAM is dominated by vote counters and one feature vector.",
    }


def run_training(data_path: str | Path, model_path: str | Path, metrics_path: str | Path) -> dict:
    x, y = load_training_data(data_path)
    x_train, x_val, x_test, y_train, y_val, y_test = stratified_split(x, y)
    model = train_random_forest(x_train, y_train)

    metrics = {
        "assumptions": [
            "Synthetic dataset is prototype-only and not final academic validation.",
            "No scaler is used because Random Forest thresholds can run directly on raw sensor units.",
            "Train/validation/test split is stratified 70/15/15. No target leakage columns are used.",
            "Desktop JSON model artifact is not deployed to ESP32.",
            "Random Forest is TinyRandomForest with random_state=42 (deterministic bootstrap and splits).",
        ],
        "features": MODEL_FEATURES,
        "raw_features": REQUIRED_SENSOR_FEATURES,
        "fusion": "Equal weight healthy pairs; single-valid fallback; unresolved disagreement blocks recommendations. Coverage is not accuracy.",
        "split_rows": {
            "train": int(len(x_train)),
            "validation": int(len(x_val)),
            "test": int(len(x_test)),
        },
        "validation": evaluate_model(model, x_val, y_val),
        "test": evaluate_model(model, x_test, y_test),
        "edge_size": model_size_summary(model),
    }

    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    Path(metrics_path).parent.mkdir(parents=True, exist_ok=True)
    Path(model_path).write_text(json.dumps(model.to_dict(MODEL_FEATURES), indent=2), encoding="utf-8")
    Path(metrics_path).write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/synthetic/soil_synthetic_prototype.csv")
    parser.add_argument("--model", default="models/soil_rf_desktop.json")
    parser.add_argument("--metrics", default="reports/metrics.json")
    args = parser.parse_args()
    metrics = run_training(args.data, args.model, args.metrics)
    print(json.dumps({"test": metrics["test"], "edge_size": metrics["edge_size"]}, indent=2))


if __name__ == "__main__":
    main()
