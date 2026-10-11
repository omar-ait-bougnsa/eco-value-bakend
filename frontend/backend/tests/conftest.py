import os

# No .env and no model key: a test that wants a model sets a key itself, and mocks the network.
os.environ['EVS_NO_DOTENV'] = '1'
os.environ['OPENROUTER_API_KEY'] = ''

# Tests run on in-memory SQLite unless TEST_DATABASE_URL points at a (disposable) PostgreSQL database.
os.environ['DATABASE_URL'] = os.getenv('TEST_DATABASE_URL', 'sqlite+pysqlite:///:memory:')
# Embeddings without a model or a network, whatever keys this machine has.
os.environ['EMBEDDINGS'] = 'hash'

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


@pytest.fixture(autouse=True)
def _calendar(monkeypatch):
    """The age of the uploads is counted to the day the demo data was loaded, whenever the tests run."""
    from app.data import seed
    from app.engine import run
    monkeypatch.setattr(run, 'real_today', lambda: seed.TODAY)


@pytest.fixture(scope='session', autouse=True)
def _schema():
    init_db()
