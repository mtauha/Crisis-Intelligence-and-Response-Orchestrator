from sqlmodel import Session
from ciro.db.models import Signal
import uuid

def write_signal(session: Session, source: str, value: dict, city: str, signal_type: str, crisis_type: str, location: dict, confidence_hint: float, verification_tag: str) -> uuid.UUID:
    signal = Signal(
        source=source, value=value, processed=False, city=city,
        signal_type=signal_type, crisis_type=crisis_type, location=location,
        confidence_hint=confidence_hint, verification_tag=verification_tag
    )
    session.add(signal)
    session.commit()
    session.refresh(signal)
    return signal.id
