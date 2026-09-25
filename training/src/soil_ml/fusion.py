"""Stateless, fail-closed fusion. Acquisition must mark stale/failed reads NaN."""
import math
import pandas as pd
from soil_ml import MODEL_FEATURES

def valid(value, low, high):
    return math.isfinite(value) and low <= value <= high

def pair(a, b, low, high, tolerance):
    av, bv = valid(a, low, high), valid(b, low, high)
    if av and bv:
        return ((a + b) / 2, "fused") if abs(a - b) <= tolerance else (float("nan"), "disagreement")
    if av or bv:
        return (a if av else b), "backup"
    return float("nan"), "missing"

def fuse(row):
    moisture, ms = pair(row["SM"], row["SMCap"], 0, 100, 15)
    temperature, ts = pair(row["ST7in1"], row["STDS18B20"], -10, 60, 5)
    features = [moisture, temperature]
    for name, high, low in [("pH", 9.5, 3.5), ("N", 200, 0), ("P", 200, 0), ("K", 250, 0), ("EC", 5, 0)]:
        value = row[name]
        features.append(value if valid(value, low, high) else float("nan"))
    available = sum(math.isfinite(v) for v in features)
    status = "normal" if available == 7 and ms == ts == "fused" else "degraded" if available == 7 else "monitor_only"
    return {"features": features, "status": status, "coverage_percent": available * 100 / 7,
            "recommendation_enabled": available == 7, "moisture": ms, "temperature": ts}

def fuse_frame(frame):
    results = [fuse(row) for _, row in frame.iterrows()]
    if not all(r["recommendation_enabled"] for r in results):
        raise ValueError("Unresolved sensor faults cannot enter crop model")
    return pd.DataFrame([r["features"] for r in results], columns=MODEL_FEATURES, index=frame.index)
