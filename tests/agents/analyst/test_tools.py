from ciro.agents.analyst.tools.read_signals import read_unprocessed_signals
from sqlmodel import Session

def test_read_unprocessed_signals(db_session: Session):
    signals = read_unprocessed_signals(db_session)
    assert isinstance(signals, list)
