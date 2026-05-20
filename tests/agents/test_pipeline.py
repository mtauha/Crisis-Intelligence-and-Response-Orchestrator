from ciro.agents.pipeline import run_pipeline
from ciro.db.models import Incident, CityState, Ticket
from sqlmodel import Session, select
import os

def test_pipeline_execution(db_session: Session, monkeypatch):
    monkeypatch.setenv("GEMINI_ENABLED", "false")
    db_session.add(CityState(city="karachi", status="normal"))
    db_session.commit()
    
    result = run_pipeline(db_session, "karachi")
    assert result is True
    
    incident = db_session.exec(select(Incident)).first()
    assert incident is not None
    assert incident.severity == "critical"
    
    state = db_session.get(CityState, "karachi")
    assert state.status == "critical"
    
    ticket = db_session.exec(select(Ticket)).first()
    assert ticket is not None
