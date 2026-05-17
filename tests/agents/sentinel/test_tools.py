from ciro.agents.sentinel.tools.read_weather import read_weather
from ciro.agents.sentinel.tools.read_social import read_social
from ciro.agents.sentinel.tools.write_signal import write_signal
from ciro.db.models import Signal
from sqlmodel import Session, select
import uuid

def test_read_weather_returns_data():
    data = read_weather("karachi")
    assert any(s.get("signal_type") == "rainfall_mm" for s in data)

def test_read_social_returns_data():
    data = read_social("karachi")
    assert isinstance(data, list)
    assert len(data) > 0

def test_write_signal(db_session: Session):
    signal_id = write_signal(
        db_session, source="weather", value={"temp": 30}, city="karachi",
        signal_type="rainfall_mm", crisis_type="urban_flooding",
        location={"lat": 24.8, "lng": 67.0}, confidence_hint=0.9, verification_tag="verified"
    )
    assert isinstance(signal_id, uuid.UUID)
    signal = db_session.exec(select(Signal).where(Signal.id == signal_id)).first()
    assert signal is not None
    assert signal.source == "weather"
