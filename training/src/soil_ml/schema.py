from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from soil_ml import PUBLIC_DATASET_FEATURES, REQUIRED_SENSOR_FEATURES


@dataclass(frozen=True)
class SchemaAudit:
    path: str
    rows: int
    columns: list[str]
    labels: list[str]
    missing_required_features: list[str]
    public_only_features: list[str]
    matching_features: list[str]
    methodological_mismatch: str


def audit_dataset_schema(csv_path: str | Path) -> SchemaAudit:
    df = pd.read_csv(csv_path)
    columns = list(df.columns)
    lower_to_original = {column.lower(): column for column in columns}

    required_lower = {feature.lower(): feature for feature in REQUIRED_SENSOR_FEATURES}
    public_lower = {feature.lower(): feature for feature in PUBLIC_DATASET_FEATURES}

    missing_required = [
        feature for key, feature in required_lower.items() if key not in lower_to_original
    ]
    public_only = [
        lower_to_original[key]
        for key in lower_to_original
        if key in public_lower and key not in required_lower
    ]
    matching = [
        lower_to_original[key]
        for key in lower_to_original
        if key in required_lower
    ]
    labels = sorted(df["label"].dropna().astype(str).unique().tolist()) if "label" in df else []

    mismatch = (
        "The public dataset records laboratory/agronomic variables "
        "(N, P, K, temperature, humidity, ph, rainfall). The FYP edge vector "
        "requires direct ESP32 sensor readings (SM, ST7in1, pH, N, P, K, EC, "
        "STDS18B20, SMCap). Missing physical measurements cannot be recovered through "
        "preprocessing without collecting or simulating those sensor channels."
    )

    return SchemaAudit(
        path=str(csv_path),
        rows=len(df),
        columns=columns,
        labels=labels,
        missing_required_features=missing_required,
        public_only_features=public_only,
        matching_features=matching,
        methodological_mismatch=mismatch,
    )


def write_schema_report(audit: SchemaAudit, output_path: str | Path) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Dataset Schema Report",
        "",
        f"- Source: `{audit.path}`",
        f"- Rows: {audit.rows}",
        f"- Columns: {', '.join(audit.columns)}",
        f"- Target labels ({len(audit.labels)}): {', '.join(audit.labels)}",
        "",
        "## Required ESP32 Sensor Vector",
        "",
        ", ".join(REQUIRED_SENSOR_FEATURES),
        "",
        "## Comparison",
        "",
        f"- Matching required features: {', '.join(audit.matching_features) or 'None'}",
        f"- Missing required features: {', '.join(audit.missing_required_features) or 'None'}",
        f"- Public-dataset-only features: {', '.join(audit.public_only_features) or 'None'}",
        "",
        "## Methodological Mismatch",
        "",
        audit.methodological_mismatch,
    ]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
