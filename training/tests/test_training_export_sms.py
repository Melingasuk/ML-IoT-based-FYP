from pathlib import Path
import json

import pandas as pd

from soil_ml import REQUIRED_SENSOR_FEATURES
from soil_ml.export_c import export_model_header
from soil_ml.publish_dashboard import publish_dashboard
from soil_ml.recommendations import SMS_RECOMMENDATIONS, sms_for_label
from soil_ml.synthetic import save_synthetic_dataset
from soil_ml.tiny_forest import TinyRandomForest
from soil_ml.train import run_training
from soil_ml.fusion import fuse_frame


def test_training_and_export_pipeline(tmp_path: Path):
    data = tmp_path / "synthetic.csv"
    model = tmp_path / "model.json"
    metrics = tmp_path / "metrics.json"
    header = tmp_path / "crop_model.h"
    meta = tmp_path / "edge_model_metadata.json"

    save_synthetic_dataset(data, rows_per_crop=30, seed=4)
    result = run_training(data, model, metrics)
    assert model.exists()
    assert metrics.exists()
    assert "TinyRandomForest" in model.read_text(encoding="utf-8")
    assert result["split_rows"] == {"train": 84, "validation": 18, "test": 18}
    assert result["edge_size"]["esp32_decision"] == "fits_prototype_budget"

    export = export_model_header(model, header, meta)
    text = header.read_text(encoding="utf-8")
    assert "predict_soil_crop" in text
    assert "TREE_OFFSETS" in text
    assert export["artifact_type"] == "ESP32-compatible C/C++ header"


def test_training_is_deterministic(tmp_path: Path):
    data = tmp_path / "synthetic.csv"
    save_synthetic_dataset(data, rows_per_crop=20, seed=7)
    first = run_training(data, tmp_path / "a.json", tmp_path / "a_metrics.json")
    second = run_training(data, tmp_path / "b.json", tmp_path / "b_metrics.json")
    assert (tmp_path / "a.json").read_text(encoding="utf-8") == (tmp_path / "b.json").read_text(encoding="utf-8")
    assert first["test"]["accuracy"] == second["test"]["accuracy"]


def test_python_and_esp32_flatten_walk_match(tmp_path: Path):
    data = tmp_path / "synthetic.csv"
    model_path = tmp_path / "model.json"
    save_synthetic_dataset(data, rows_per_crop=20, seed=3)
    run_training(data, model_path, tmp_path / "metrics.json")
    model = TinyRandomForest.from_dict(json.loads(model_path.read_text(encoding="utf-8")))
    rows = fuse_frame(pd.read_csv(data)).to_numpy(dtype=float)[:12]
    assert model.predict_indices(rows) == model.predict_indices_flattened(rows)


def test_publish_dashboard_copies_metrics(tmp_path: Path):
    metrics = tmp_path / "metrics.json"
    dashboard = tmp_path / "dashboard"
    metrics.write_text(
        '{"test": {"accuracy": 0.9}, "edge_size": {"esp32_decision": "fits_prototype_budget"}}',
        encoding="utf-8",
    )
    result = publish_dashboard(metrics, dashboard)
    assert (dashboard / "metrics.json").exists()
    assert result["test_accuracy"] == 0.9


def test_sms_messages_fit_sim800c_limit():
    for label, message in SMS_RECOMMENDATIONS.items():
        assert sms_for_label(label) == message
        assert len(message) <= 160
