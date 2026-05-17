from sqlmodel import Session
from ciro.db.models import Ticket
import uuid

def issue_ticket(session: Session, incident_id: uuid.UUID, title: str, authority: str) -> uuid.UUID:
    ticket = Ticket(incident_id=incident_id, title=title, authority=authority)
    session.add(ticket)
    session.commit()
    return ticket.id
