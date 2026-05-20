import os
from sqlmodel import Session
from ciro.agents.sentinel.sentinel_agent import SentinelAgent
from ciro.agents.analyst.analyst_agent import AnalystAgent
from ciro.agents.commander.commander_agent import CommanderAgent
from ciro.stubs.record_stubs import load_stub
from ciro.agents.sentinel.tools.write_signal import write_signal
from ciro.agents.analyst.tools.write_incident import write_incident

def run_pipeline(session: Session, scenario: str) -> bool:
    gemini_enabled = os.environ.get("GEMINI_ENABLED", "true").lower() == "true"
    
    if not gemini_enabled:
        sentinel_stub = load_stub("sentinel", scenario)
        if sentinel_stub:
            write_signal(session, "weather", sentinel_stub.get("value", {}), scenario, "rainfall_mm", "urban_flooding", {"lat": 24.8, "lng": 67.0}, 0.9, "verified")
            
        analyst_stub = load_stub("analyst", scenario)
        if analyst_stub:
            incident_id = write_incident(
                session, "urban_flooding", scenario, analyst_stub.get("severity", "critical"), 
                0.95, analyst_stub.get("reasoning", "Stub reason"), {}
            )
            CommanderAgent().execute(session, incident_id)
        return True
    
    return True
