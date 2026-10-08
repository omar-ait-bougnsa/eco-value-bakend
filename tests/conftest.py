import os

# Tests run on in-memory SQLite unless TEST_DATABASE_URL points at a (disposable) PostgreSQL database.
os.environ['DATABASE_URL'] = os.getenv('TEST_DATABASE_URL', 'sqlite+pysqlite:///:memory:')

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.store import Store, init_db  # noqa: E402


@pytest.fixture
def store():
    """A store on freshly seeded demo data."""
    db.Base.metadata.create_all(db.engine)
    with db.SessionLocal() as session:
        s = Store(session)
        s.reset()
        yield s


@pytest.fixture(scope='session', autouse=True)
def _schema():
    init_db()
