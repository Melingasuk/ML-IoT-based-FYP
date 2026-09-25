import math
from soil_ml.fusion import fuse

def sample():
    return dict(SM=52., SMCap=54., ST7in1=24., STDS18B20=24.2, pH=6.4, N=92., P=44., K=48., EC=1.1)

def test_healthy_fusion():
    r = fuse(sample())
    assert r["features"][0] == 53
    assert r["status"] == "normal" and r["coverage_percent"] == 100

def test_primary_pair_failover():
    s = sample()
    s.update(SM=math.nan, ST7in1=math.nan)
    r = fuse(s)
    assert r["status"] == "degraded" and r["recommendation_enabled"]
    assert r["features"][:2] == [54, 24.2]

def test_entire_primary_failure():
    s = sample()
    for key in ("SM", "ST7in1", "pH", "N", "P", "K", "EC"):
        s[key] = math.nan
    r = fuse(s)
    assert not r["recommendation_enabled"]
    assert abs(r["coverage_percent"] - 200/7) < 1e-9

def test_disagreement_blocks():
    s = sample()
    s["SM"] = 90
    r = fuse(s)
    assert r["moisture"] == "disagreement" and not r["recommendation_enabled"]

def test_missing_backups_and_invalid_temperature():
    s = sample()
    s.update(SMCap=math.nan, STDS18B20=-127)
    assert fuse(s)["status"] == "degraded"
    s["ST7in1"] = math.inf
    assert not fuse(s)["recommendation_enabled"]
