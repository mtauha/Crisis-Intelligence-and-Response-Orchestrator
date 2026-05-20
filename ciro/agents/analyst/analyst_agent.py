from google.adk.agents import LlmAgent
from ciro.agents.analyst.tools.read_signals import read_unprocessed_signals
from ciro.agents.analyst.tools.check_incident import check_incident_exists
from ciro.agents.analyst.tools.write_incident import write_incident
from ciro.agents.analyst.tools.mark_processed import mark_signals_processed

class AnalystAgent(LlmAgent):
    def __init__(self):
        super().__init__(
            name="Analyst",
            tools=[read_unprocessed_signals, check_incident_exists, write_incident, mark_signals_processed],
            instruction="""You are the Analyst Crisis Detector.
Correlate signals to determine crisis threshold breaches. Output structured severity and confidence."""
        )
