from sqlmodel import Session, select
from ciro.db.models import Route

def block_flood_routes(session: Session, city: str) -> bool:
    routes = session.exec(select(Route).where(Route.city == city)).all()
    for route in routes:
        route.status = "blocked"
    session.commit()
    return True
