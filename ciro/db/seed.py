import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import select
from ciro.db.models import CityState, Route
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/ciro")
engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def seed():
    async with SessionLocal() as session:
        # Check idempotency for Karachi
        result = await session.exec(select(CityState).where(CityState.city == "karachi"))
        if not result.first():
            # Seed Karachi City State
            karachi_state = CityState(city="karachi", status="normal", active_incidents=0)
            session.add(karachi_state)
            
            # Seed Routes
            route1 = Route(
                city="karachi", route_name="Gulshan Underpass", status="open",
                original_path={"type": "LineString", "coordinates": [[67.0946, 24.9215], [67.0950, 24.9220]]}
            )
            route2 = Route(
                city="karachi", route_name="Nazimabad Route", status="open",
                original_path={"type": "LineString", "coordinates": [[67.0439, 24.9056], [67.0450, 24.9060]]}
            )
            session.add(route1)
            session.add(route2)
            
            await session.commit()
            print("Seed data inserted successfully.")
        else:
            print("Seed data already exists.")

if __name__ == "__main__":
    asyncio.run(seed())
