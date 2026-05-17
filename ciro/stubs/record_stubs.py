import json
import os
import pathlib

def load_stub(agent_name: str, scenario: str) -> dict:
    stub_path = pathlib.Path(__file__).parent / f"{agent_name.lower()}_{scenario}.json"
    if stub_path.exists():
        with open(stub_path, "r") as f:
            return json.load(f)
    return {}

def save_stub(agent_name: str, scenario: str, data: dict):
    stub_path = pathlib.Path(__file__).parent / f"{agent_name.lower()}_{scenario}.json"
    with open(stub_path, "w") as f:
        json.dump(data, f, indent=2)
