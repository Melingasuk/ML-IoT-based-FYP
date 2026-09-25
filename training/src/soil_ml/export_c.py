from __future__ import annotations

import argparse
import json
from pathlib import Path

from soil_ml import MODEL_FEATURES as REQUIRED_SENSOR_FEATURES
from soil_ml.tiny_forest import TinyRandomForest


def load_tiny_forest(model_path: str | Path) -> TinyRandomForest:
    payload = json.loads(Path(model_path).read_text(encoding="utf-8"))
    if payload.get("model_type") != "TinyRandomForest":
        raise ValueError(
            "Expected a TinyRandomForest JSON artifact. Retrain with "
            "`python -m soil_ml.cli train` instead of a sklearn joblib pickle."
        )
    if payload.get("features") != REQUIRED_SENSOR_FEATURES:
        raise ValueError(
            f"Model features {payload.get('features')} do not match "
            f"ESP32 sensor vector {REQUIRED_SENSOR_FEATURES}."
        )
    return TinyRandomForest.from_dict(payload)


def export_model_header(model_bundle_path: str | Path, output_header: str | Path, metadata_path: str | Path) -> dict:
    model = load_tiny_forest(model_bundle_path)
    packed = model.flatten_for_esp32()
    class_names = list(model.classes_)

    header = Path(output_header)
    header.parent.mkdir(parents=True, exist_ok=True)

    def arr(name: str, ctype: str, values_list, fmt=str) -> str:
        body = ", ".join(fmt(value) for value in values_list)
        return f"static const {ctype} {name}[] PROGMEM = {{{body}}};"

    lines = [
        "#pragma once",
        "#include <Arduino.h>",
        "#include <pgmspace.h>",
        "",
        "// Auto-generated TinyRandomForest. Do not edit by hand.",
        "// Source model: prototype Random Forest trained on synthetic sensor data.",
        "// Layout: TREE_LEFT/TREE_RIGHT are indices within each tree; add TREE_OFFSETS[t].",
        f"static const uint8_t SOIL_FEATURE_COUNT = {len(REQUIRED_SENSOR_FEATURES)};",
        f"static const uint8_t SOIL_CLASS_COUNT = {len(class_names)};",
        f"static const uint8_t SOIL_TREE_COUNT = {len(packed['offsets'])};",
        "",
        arr("TREE_OFFSETS", "uint16_t", packed["offsets"]),
        arr("TREE_FEATURE", "int8_t", packed["features"]),
        arr("TREE_LEFT", "int16_t", packed["lefts"]),
        arr("TREE_RIGHT", "int16_t", packed["rights"]),
        arr("TREE_VALUE", "int8_t", packed["values"]),
        arr("TREE_THRESHOLD", "float", packed["thresholds"], lambda value: f"{value:.9e}f"),
        "",
        "static const char* const SOIL_CLASS_NAMES[] = {"
        + ", ".join(f'\"{name}\"' for name in class_names)
        + "};",
        "",
        "inline int predict_soil_crop(const float x[SOIL_FEATURE_COUNT]) {",
        "  uint8_t votes[SOIL_CLASS_COUNT] = {0};",
        "  for (uint8_t t = 0; t < SOIL_TREE_COUNT; ++t) {",
        "    uint16_t base = pgm_read_word(&TREE_OFFSETS[t]);",
        "    int node = (int)base;",
        "    while (true) {",
        "      int8_t feature = (int8_t)pgm_read_byte(&TREE_FEATURE[node]);",
        "      if (feature < 0) {",
        "        int8_t klass = (int8_t)pgm_read_byte(&TREE_VALUE[node]);",
        "        votes[klass]++;",
        "        break;",
        "      }",
        "      float threshold = pgm_read_float(&TREE_THRESHOLD[node]);",
        "      int16_t child = x[feature] <= threshold",
        "        ? (int16_t)pgm_read_word(&TREE_LEFT[node])",
        "        : (int16_t)pgm_read_word(&TREE_RIGHT[node]);",
        "      node = (int)child + (int)base;",
        "    }",
        "  }",
        "  uint8_t best = 0;",
        "  for (uint8_t i = 1; i < SOIL_CLASS_COUNT; ++i) {",
        "    if (votes[i] > votes[best]) best = i;",
        "  }",
        "  return best;",
        "}",
        "",
    ]
    header.write_text("\n".join(lines), encoding="utf-8")

    metadata = {
        "features": REQUIRED_SENSOR_FEATURES,
        "classes": class_names,
        "tree_count": len(packed["offsets"]),
        "total_nodes": len(packed["features"]),
        "artifact_type": "ESP32-compatible C/C++ header",
        "source_artifact": "TinyRandomForest JSON (not sklearn joblib)",
        "desktop_pickle_warning": ".joblib/.pkl artifacts are not used. ESP32 loads crop_model.h only.",
    }
    meta = Path(metadata_path)
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/soil_rf_desktop.json")
    parser.add_argument("--header", default="firmware/esp32_soil_edge/include/crop_model.h")
    parser.add_argument("--metadata", default="models/edge_model_metadata.json")
    args = parser.parse_args()
    print(json.dumps(export_model_header(args.model, args.header, args.metadata), indent=2))


if __name__ == "__main__":
    main()
