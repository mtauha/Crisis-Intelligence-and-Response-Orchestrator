from sqlmodel import Session, select
from ciro.db.models import CityState

def escalate_city_state(session: Session, city: str) -> bool:
    state = session.exec(select(CityState).where(CityState.city == city)).first()
    if state:
        state.status = "critical"
        session.commit()
        return True
    return False
