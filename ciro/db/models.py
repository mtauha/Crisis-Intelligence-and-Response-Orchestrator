from sqlmodel import SQLModel, Field
from sqlalchemy import Column, TEXT
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ARRAY, JSONB
from typing import Optional, List
from datetime import datetime
import uuid

class Signal(SQLModel, table=True):
    __tablename__ = "signals"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    city: str
    source: str
    signal_type: str
    crisis_type: str
    value: dict = Field(sa_column=Column(JSONB))
    location: dict = Field(sa_column=Column(JSONB))
    confidence_hint: float
    verification_tag: str
    cross_referenced_with: List[uuid.UUID] = Field(default=[], sa_column=Column(ARRAY(PG_UUID(as_uuid=True))))
    raw_text: Optional[str] = None
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    processed: bool = Field(default=False)

class Incident(SQLModel, table=True):
    __tablename__ = "incidents"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    city: str
    crisis_type: str
    severity: str
    status: str
    confidence: float
    reasoning: str
    evidence_summary: dict = Field(sa_column=Column(JSONB))
    affected_zones: List[str] = Field(default=[], sa_column=Column(ARRAY(TEXT)))
    signal_ids: List[uuid.UUID] = Field(default=[], sa_column=Column(ARRAY(PG_UUID(as_uuid=True))))
    # Per-incident before/after diff. Feeds the Incident Detail screen.
    state_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None

class CityState(SQLModel, table=True):
    __tablename__ = "city_state"
    city: str = Field(primary_key=True)
    status: str = Field(default="normal")
    active_incidents: int = Field(default=0)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    # Current live city state snapshot. Feeds the Home screen.
    state_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSONB))

class Action(SQLModel, table=True):
    __tablename__ = "actions"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    incident_id: uuid.UUID = Field(foreign_key="incidents.id")
    action_type: str
    payload: dict = Field(sa_column=Column(JSONB))
    executed_at: datetime = Field(default_factory=datetime.utcnow)

class Ticket(SQLModel, table=True):
    __tablename__ = "tickets"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    incident_id: uuid.UUID = Field(foreign_key="incidents.id")
    title: str
    status: str = Field(default="open")
    authority: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Route(SQLModel, table=True):
    __tablename__ = "routes"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    city: str
    route_name: str
    status: str = Field(default="open")
    original_path: dict = Field(sa_column=Column(JSONB))
    rerouted_path: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    updated_at: datetime = Field(default_factory=datetime.utcnow)
