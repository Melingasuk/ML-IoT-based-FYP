"""Soil monitoring ML workflow for ESP32 edge deployment."""

REQUIRED_SENSOR_FEATURES = [
    "SM",
    "ST7in1",
    "pH",
    "N",
    "P",
    "K",
    "EC",
    "STDS18B20",
    "SMCap",
]

MODEL_FEATURES = ["SMFused", "STFused", "pH", "N", "P", "K", "EC"]

PUBLIC_DATASET_FEATURES = ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"]
