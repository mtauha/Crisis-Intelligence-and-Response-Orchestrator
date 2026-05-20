from ciro.agents.sentinel.sentinel_agent import SentinelAgent
from ciro.agents.sentinel.tools.read_weather import read_weather

def test_sentinel_initialization():
    agent = SentinelAgent()
    assert agent.name == "Sentinel"
    assert read_weather in agent.tools
