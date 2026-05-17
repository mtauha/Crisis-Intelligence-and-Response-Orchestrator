from sqlmodel import Session
from ciro.db.models import Signal
import uuid

def mark_signals_processed(session: Session, signal_ids: list[uuid.UUID]):
    for signal_id in signal_ids:
        signal = session.get(Signal, signal_id)
        if signal:
            signal.processed = True
    session.commit()
