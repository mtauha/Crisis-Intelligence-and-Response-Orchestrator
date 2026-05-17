from ciro.agents.commander.commander_agent import CommanderAgent
from sqlmodel import Session
import uuid

def test_commander_agent_idempotent(db_session: Session):
    agent = CommanderAgent()
    assert agent.execute(db_session, incident_id=uuid.uuid4()) is False
