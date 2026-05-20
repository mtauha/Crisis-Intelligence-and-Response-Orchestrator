from ciro.agents.analyst.analyst_agent import AnalystAgent
from ciro.agents.analyst.tools.read_signals import read_unprocessed_signals

def test_analyst_initialization():
    agent = AnalystAgent()
    assert agent.name == "Analyst"
    assert read_unprocessed_signals in agent.tools
