from __future__ import annotations

import argparse
import json
from pathlib import Path

from soil_ml.schema import audit_dataset_schema, write_schema_report
from soil_ml.synthetic import save_synthetic_dataset


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit")
    audit.add_argument("--dataset", required=True)
    audit.add_argument("--out", default="reports/dataset_schema_report.md")

    synth = sub.add_parser("synthetic")
    synth.add_argument("--out", default="data/synthetic/soil_synthetic_prototype.csv")
    synth.add_argument("--rows-per-crop", type=int, default=250)
    synth.add_argument("--seed", type=int, default=42)

    train = sub.add_parser("train")
    train.add_argument("--data", default="data/synthetic/soil_synthetic_prototype.csv")
    train.add_argument("--model", default="models/soil_rf_desktop.json")
    train.add_argument("--metrics", default="reports/metrics.json")

    export = sub.add_parser("export")
    export.add_argument("--model", default="models/soil_rf_desktop.json")
    export.add_argument("--header", default="firmware/esp32_soil_edge/include/crop_model.h")
    export.add_argument("--metadata", default="models/edge_model_metadata.json")

    dashboard = sub.add_parser("publish-dashboard")
    dashboard.add_argument("--metrics", default="reports/metrics.json")
    dashboard.add_argument("--dashboard", default="dashboard")

    args = parser.parse_args()
    if args.command == "audit":
        result = audit_dataset_schema(args.dataset)
        write_schema_report(result, args.out)
        print(json.dumps(result.__dict__, indent=2))
    elif args.command == "synthetic":
        df = save_synthetic_dataset(args.out, rows_per_crop=args.rows_per_crop, seed=args.seed)
        print(json.dumps({"out": str(Path(args.out)), "rows": len(df), "columns": list(df.columns)}, indent=2))
    elif args.command == "train":
        from soil_ml.train import run_training

        print(json.dumps(run_training(args.data, args.model, args.metrics), indent=2))
    elif args.command == "export":
        from soil_ml.export_c import export_model_header

        print(json.dumps(export_model_header(args.model, args.header, args.metadata), indent=2))
    elif args.command == "publish-dashboard":
        from soil_ml.publish_dashboard import publish_dashboard

        print(json.dumps(publish_dashboard(args.metrics, args.dashboard), indent=2))


if __name__ == "__main__":
    main()
