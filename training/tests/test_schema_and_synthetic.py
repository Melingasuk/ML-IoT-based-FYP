from pathlib import Path

from soil_ml import REQUIRED_SENSOR_FEATURES
from soil_ml.schema import audit_dataset_schema
from soil_ml.synthetic import generate_synthetic_dataset, save_synthetic_dataset


def test_synthetic_dataset_schema(tmp_path: Path):
    output = tmp_path / "synthetic.csv"
    df = save_synthetic_dataset(output, rows_per_crop=5, seed=1)
    assert output.exists()
    assert list(df.columns) == REQUIRED_SENSOR_FEATURES + ["label"]
    assert df["label"].nunique() >= 4


def test_public_schema_detects_missing_required_columns(tmp_path: Path):
    sample = tmp_path / "public.csv"
    sample.write_text("N,P,K,temperature,humidity,ph,rainfall,label\n1,2,3,25,70,6.5,100,maize\n", encoding="utf-8")
    audit = audit_dataset_schema(sample)
    assert "SM" in audit.missing_required_features
    assert "EC" in audit.missing_required_features
    assert "STDS18B20" in audit.missing_required_features
    assert "N" in audit.matching_features


def test_synthetic_ranges_are_valid():
    df = generate_synthetic_dataset(rows_per_crop=20, seed=2)
    assert df["SM"].between(0, 100).all()
    assert df["pH"].between(3.5, 9.5).all()
    assert df["EC"].between(0, 5).all()
