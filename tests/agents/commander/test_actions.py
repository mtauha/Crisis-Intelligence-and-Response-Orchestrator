from ciro.agents.commander.actions.city_state import escalate_city_state
from ciro.db.models import CityState
from sqlmodel import Session

def test_escalate_city_state(db_session: Session):
    db_session.add(CityState(city="karachi", status="normal"))
    db_session.commit()
    success = escalate_city_state(db_session, "karachi")
    assert success is True
    state = db_session.get(CityState, "karachi")
    assert state.status == "critical"
