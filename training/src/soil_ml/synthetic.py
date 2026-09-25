from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from soil_ml import REQUIRED_SENSOR_FEATURES


@dataclass(frozen=True)
class CropProfile:
    label: str
    means: dict[str, float]
    stds: dict[str, float]


PROTOTYPE_PROFILES = [
    CropProfile(
        "maize",
        {"SM": 48, "ST7in1": 24, "pH": 6.4, "N": 90, "P": 45, "K": 45, "EC": 1.1, "STDS18B20": 24},
        {"SM": 8, "ST7in1": 2.5, "pH": 0.35, "N": 18, "P": 10, "K": 10, "EC": 0.25, "STDS18B20": 2.3},
    ),
    CropProfile(
        "banana",
        {"SM": 68, "ST7in1": 27, "pH": 6.1, "N": 105, "P": 55, "K": 135, "EC": 1.5, "STDS18B20": 27},
        {"SM": 7, "ST7in1": 2.0, "pH": 0.3, "N": 20, "P": 11, "K": 22, "EC": 0.3, "STDS18B20": 2.0},
    ),
    CropProfile(
        "kidneybeans",
        {"SM": 42, "ST7in1": 22, "pH": 6.0, "N": 35, "P": 62, "K": 32, "EC": 0.8, "STDS18B20": 22},
        {"SM": 7, "ST7in1": 2.2, "pH": 0.35, "N": 12, "P": 12, "K": 8, "EC": 0.2, "STDS18B20": 2.1},
    ),
    CropProfile(
        "cabbage",
        {"SM": 60, "ST7in1": 20, "pH": 6.7, "N": 80, "P": 50, "K": 70, "EC": 1.2, "STDS18B20": 20},
        {"SM": 8, "ST7in1": 2.0, "pH": 0.3, "N": 16, "P": 10, "K": 14, "EC": 0.25, "STDS18B20": 2.0},
    ),
]

RANGES = {
    "SM": (0.0, 100.0),
    "SMCap": (0.0, 100.0),
    "ST7in1": (-10.0, 60.0),
    "pH": (3.5, 9.5),
    "N": (0.0, 200.0),
    "P": (0.0, 200.0),
    "K": (0.0, 250.0),
    "EC": (0.0, 5.0),
    "STDS18B20": (-10.0, 60.0),
}


def generate_synthetic_dataset(rows_per_crop: int = 250, seed: int = 42) -> pd.DataFrame:
    """Generate clearly labeled prototype-only sensor data.

    This is not field data and must not be used as final academic validation.
    """
    rng = np.random.default_rng(seed)
    frames: list[pd.DataFrame] = []
    for profile in PROTOTYPE_PROFILES:
        data = {}
        for feature in REQUIRED_SENSOR_FEATURES:
            if feature in ("SMCap", "STDS18B20"):
                continue
            values = rng.normal(profile.means[feature], profile.stds[feature], rows_per_crop)
            low, high = RANGES[feature]
            data[feature] = np.clip(values, low, high)
        # Shared simulated physical quantities with independent measurement noise.
        data["SMCap"] = np.clip(data["SM"] + rng.normal(0, 2, rows_per_crop), 0, 100)
        data["STDS18B20"] = np.clip(data["ST7in1"] + rng.normal(0, 0.4, rows_per_crop), -10, 60)
        data["label"] = profile.label
        frames.append(pd.DataFrame(data))
    df = pd.concat(frames, ignore_index=True)
    return df[REQUIRED_SENSOR_FEATURES + ["label"]].sample(frac=1.0, random_state=seed).reset_index(drop=True)


def save_synthetic_dataset(output_path: str | Path, rows_per_crop: int = 250, seed: int = 42) -> pd.DataFrame:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    df = generate_synthetic_dataset(rows_per_crop=rows_per_crop, seed=seed)
    df.to_csv(output, index=False)
    return df
