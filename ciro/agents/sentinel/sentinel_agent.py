from google.adk.agents import LlmAgent
from ciro.agents.sentinel.tools.read_weather import read_weather
from ciro.agents.sentinel.tools.read_social import read_social
from ciro.agents.sentinel.tools.write_signal import write_signal

class SentinelAgent(LlmAgent):
    def __init__(self):
        super().__init__(
            name="Sentinel",
            tools=[read_weather, read_social, write_signal],
            instruction="""You are the Sentinel Data Ingestion Agent. 
Gather weather and social signals, filter noise, and look for Roman Urdu keywords.
Write valid signals to the database."""
        )
