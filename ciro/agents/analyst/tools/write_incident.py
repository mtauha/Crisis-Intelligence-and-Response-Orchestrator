from sqlmodel import Session
from ciro.db.models import Incident
import uuid

def write_incident(session: Session, crisis_type: str, city: str, severity: str, confidence: float, reasoning: str, evidence_summary: dict) -> uuid.UUID:
    incident = Incident(crisis_type=crisis_type, city=city, severity=severity, confidence=confidence, reasoning=reasoning, evidence_summary=evidence_summary, status="pending_commander")
    session.add(incident)
    session.commit()
    session.refresh(incident)
    return incident.id
