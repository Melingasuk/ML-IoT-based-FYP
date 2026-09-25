from pathlib import Path


def test_firmware_contains_required_validation_hooks():
    firmware = Path("firmware/esp32_soil_edge/src/main.cpp").read_text(encoding="utf-8")
    assert "fuseSensors" in firmware
    assert "temp disagreement" in firmware
    assert "predict_soil_crop" in firmware
    assert "SIM800C" in firmware
