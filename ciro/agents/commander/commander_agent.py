from google.adk.agents import BaseAgent
from sqlmodel import Session
from ciro.db.models import Incident
from ciro.agents.commander.actions.city_state import escalate_city_state
from ciro.agents.commander.actions.routes import block_flood_routes
from ciro.agents.commander.actions.tickets import issue_ticket
import uuid

class CommanderAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="Commander")

    def execute(self, session: Session, incident_id: uuid.UUID) -> bool:
        incident = session.get(Incident, incident_id)
        if not incident or incident.status not in ["pending_commander", "approved"]:
            return False
            
        city = incident.city
        escalate_city_state(session, city)
        block_flood_routes(session, city)
        issue_ticket(session, incident_id, title="Flood response blocked routes", authority="City Traffic")
        
        incident.status = "actioned"
        session.commit()
        return True
