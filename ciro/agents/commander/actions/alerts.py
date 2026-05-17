from sqlmodel import Session
from ciro.db.models import Action
import uuid

def broadcast_alert(session: Session, incident_id: uuid.UUID, message: str) -> uuid.UUID:
    action = Action(incident_id=incident_id, action_type="ALERT", payload={"message": message})
    session.add(action)
    session.commit()
    return action.id
