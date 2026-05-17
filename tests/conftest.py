import pytest
from sqlmodel import SQLModel, Session, create_engine
from ciro.db.models import *
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres_container():
    postgres = PostgresContainer("postgres:15-alpine")
    postgres.start()
    yield postgres
    postgres.stop()

@pytest.fixture(name="db_session")
def db_session_fixture(postgres_container):
    engine = create_engine(postgres_container.get_connection_url(driver="psycopg2"))
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)

