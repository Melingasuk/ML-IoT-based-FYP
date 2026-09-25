"""Synthetic held-out fault injection; no test-time retraining."""
import json
from pathlib import Path
import numpy as np
from soil_ml.train import load_training_data, stratified_split, evaluate_model
from soil_ml.export_c import load_tiny_forest
from soil_ml.fusion import fuse
x, y = load_training_data("data/synthetic/soil_synthetic_prototype.csv")
_, _, test, _, _, labels = stratified_split(x, y)
model = load_tiny_forest("models/soil_rf_desktop.json")
report = {"warning": "Synthetic only; coverage is not accuracy.", "scenarios": {}}
for name, failed in {"normal": [], "primary_moisture_failed": ["SM"], "primary_temperature_failed": ["ST7in1"], "primary_pair_failed": ["SM", "ST7in1"], "backups_failed": ["SMCap", "STDS18B20"], "whole_7in1_failed": ["SM", "ST7in1", "pH", "N", "P", "K", "EC"], "moisture_disagreement": []}.items():
    frame = test.copy()
    for column in failed:
        frame[column] = np.nan
    if name == "moisture_disagreement":
        frame["SM"] = np.where(frame["SMCap"] < 50, 95, 5)
    states = [fuse(row) for _, row in frame.iterrows()]
    enabled = [r["recommendation_enabled"] for r in states]
    result = {"rows": len(frame), "recommendations_enabled": sum(enabled), "mean_coverage_percent": float(np.mean([r["coverage_percent"] for r in states]))}
    if any(enabled):
        result["metrics"] = evaluate_model(model, frame.loc[enabled].reset_index(drop=True), labels.loc[enabled].reset_index(drop=True))
    report["scenarios"][name] = result
Path("reports/fault_metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({k: {"enabled": v["recommendations_enabled"], "coverage": v["mean_coverage_percent"], "accuracy": v.get("metrics", {}).get("accuracy")} for k,v in report["scenarios"].items()}, indent=2))
