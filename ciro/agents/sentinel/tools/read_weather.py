import json
import pathlib

def read_weather(city: str) -> list[dict]:
    mock_path = pathlib.Path(__file__).parent.parent.parent.parent.parent / "mock_data" / "weather_signals.json"
    if not mock_path.exists():
        return []
    with open(mock_path, "r") as f:
        data = json.load(f).get("signals", [])
        return [s for s in data if s.get("city") == city]
