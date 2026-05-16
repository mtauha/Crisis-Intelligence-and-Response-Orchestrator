import json
import os

def test_weather_signals():
    path = os.path.join("ciro", "mock_data", "weather_signals.json")
    with open(path) as f:
        data = json.load(f)
    assert "signals" in data
    assert data["signals"][0]["value"] == 87.4

def test_social_signals():
    path = os.path.join("ciro", "mock_data", "social_signals.json")
    with open(path) as f:
        data = json.load(f)
    assert len(data["signals"]) == 2
