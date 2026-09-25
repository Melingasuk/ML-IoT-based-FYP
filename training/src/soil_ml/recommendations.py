from __future__ import annotations

SMS_RECOMMENDATIONS = {
    "banana": "Banana OK: keep soil moist, add K-rich manure, monitor pH/EC.",
    "cabbage": "Cabbage OK: keep cool moist soil, add N compost, avoid waterlogging.",
    "kidneybeans": "Beans OK: moderate moisture, avoid excess N, keep pH near 6.",
    "maize": "Maize OK: add compost/NPK, keep moderate moisture, weed early.",
}

DETAILED_RECOMMENDATIONS = {
    "banana": "Recommended crop: banana. Maintain high soil moisture, prioritize potassium, and monitor EC to avoid salinity stress.",
    "cabbage": "Recommended crop: cabbage. Maintain cool and moist soil, add nitrogen-rich compost, and avoid waterlogging.",
    "kidneybeans": "Recommended crop: kidneybeans. Maintain moderate moisture, avoid excessive nitrogen, and keep pH near neutral.",
    "maize": "Recommended crop: maize. Maintain moderate soil moisture, add compost or balanced NPK, and weed early.",
}


def sms_for_label(label: str) -> str:
    text = SMS_RECOMMENDATIONS.get(label, f"Crop: {label}. Check soil pH, moisture, NPK, and EC before planting.")
    if len(text) > 160:
        raise ValueError(f"SMS recommendation for {label} is {len(text)} chars")
    return text
