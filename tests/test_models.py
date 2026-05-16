import uuid
from ciro.db.models import Signal, Incident, CityState, Action, Ticket, Route

def test_models_instantiation():
    cs = CityState(city="karachi", status="normal", active_incidents=0)
    assert cs.city == "karachi"
    
    sig = Signal(city="karachi", source="weather", signal_type="rain", crisis_type="urban_flooding", value={"rain": 10}, location={"lat": 0, "lng": 0}, confidence_hint=0.9, verification_tag="VERIFIED")
    assert sig.value["rain"] == 10
    
    inc = Incident(id=uuid.uuid4(), city="karachi", crisis_type="flood", severity="low", status="feed_only", confidence=0.5, reasoning="test", evidence_summary={"a": "b"})
    assert inc.severity == "low"
    
    act = Action(incident_id=inc.id, action_type="ticket", payload={"foo": "bar"})
    assert act.payload["foo"] == "bar"
    
    tkt = Ticket(incident_id=inc.id, title="Test", authority="NDMA")
    assert tkt.status == "open"
    
    rt = Route(city="karachi", route_name="Route A", original_path={"type": "LineString"})
    assert rt.status == "open"
