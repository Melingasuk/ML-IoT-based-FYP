from __future__ import annotations

import json
from pathlib import Path


def publish_dashboard(
    metrics_path: str | Path = "reports/metrics.json",
    dashboard_dir: str | Path = "dashboard",
) -> dict:
    metrics_file = Path(metrics_path)
    if not metrics_file.exists():
        raise FileNotFoundError(f"Train first so {metrics_file} exists.")
    dashboard = Path(dashboard_dir)
    dashboard.mkdir(parents=True, exist_ok=True)
    payload = json.loads(metrics_file.read_text(encoding="utf-8"))
    target = dashboard / "metrics.json"
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {
        "metrics": str(metrics_file),
        "dashboard_metrics": str(target),
        "test_accuracy": payload.get("test", {}).get("accuracy"),
        "esp32_decision": payload.get("edge_size", {}).get("esp32_decision"),
    }
