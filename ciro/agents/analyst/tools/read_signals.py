from sqlmodel import Session, select
from ciro.db.models import Signal

def read_unprocessed_signals(session: Session) -> list[Signal]:
    return session.exec(select(Signal).where(Signal.processed == False)).all()
