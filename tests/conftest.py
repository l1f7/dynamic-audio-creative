"""Shared test fixtures."""

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db as _db
from app.models import AdminUser


@pytest.fixture(scope="session")
def app():
    """Create the Flask app with test config."""
    app = create_app("testing")
    yield app


@pytest.fixture(scope="function")
def db(app):
    """Fresh database for each test — creates all tables, rolls back after."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture(scope="function")
def client(app, db):
    """Flask test client with an active database."""
    with app.test_client() as client:
        with app.app_context():
            yield client


@pytest.fixture(scope="function")
def authenticated_client(client, app):
    """Test client that's already logged in."""
    user = AdminUser(
        email="admin@example.com",
        full_name="Admin User",
        password_hash=generate_password_hash("changeme12345"),
        is_active=True,
        must_change_password=False,
    )
    _db.session.add(user)
    _db.session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = f"user:{user.id}"
        sess["_fresh"] = True
    yield client
