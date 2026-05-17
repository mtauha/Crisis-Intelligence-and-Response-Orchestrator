from sqlmodel import Session, select
from ciro.db.models import Incident

def check_incident_exists(session: Session, crisis_type: str, city: str) -> Incident | None:
    return session.exec(select(Incident).where(Incident.crisis_type == crisis_type, Incident.city == city, Incident.status != "resolved")).first()
