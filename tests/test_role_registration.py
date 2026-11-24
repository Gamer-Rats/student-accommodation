
"""Task #29: role-safe public registration tests."""

import pytest

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select
from sqlalchemy.pool import StaticPool

from app.database import get_session
from app.main import app
from app.models.student_application import StudentApplication
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.auth_service import AuthService
from app.services.student_eligibility import student_access_error
from app.utilities.security import verify_password


@pytest.fixture
def isolated_registration_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )

    SQLModel.metadata.create_all(engine)

    def test_session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = test_session_override

    try:
        yield engine
    finally:
        app.dependency_overrides.pop(get_session, None)
        SQLModel.metadata.drop_all(engine)
        engine.dispose()


def register(
    client,
    *,
    role="student",
    entry_path="registered",
    student_id="202012345",
    username="alice",
    email="alice@example.com",
    password="secret123"
):
    return client.post(
        "/register",
        data={
            "username": username,
            "email": email,
            "password": password,
            "role": role,
            "entry_path": entry_path,
            "student_id": student_id,
        },
    )


def test_student_signup_records_unverified_claim(
    isolated_registration_db
):
    client = TestClient(app, follow_redirects=False)

    response = register(client)

    assert response.status_code == 303
    assert response.headers["location"].endswith("/login")

    with Session(isolated_registration_db) as db:
        user = db.exec(
            select(User).where(User.username == "alice")
        ).one()

        claim = db.exec(
            select(StudentApplication).where(
                StudentApplication.user_id == user.id
            )
        ).one()

        assert user.role == "student"
        assert user.student_id is None
        assert user.provisional == 0

        assert claim.entry_path == "registered"
        assert claim.claimed_student_id == "202012345"
        assert claim.status == "pending"

        assert student_access_error(
            user.model_dump()
        ) == "student eligibility required"

        assert verify_password(
            "secret123",
            user.password
        )

    login = client.post(
        "/login",
        data={
            "username": "alice",
            "password": "secret123"
        }
    )

    assert login.status_code == 303
    assert login.headers["location"].endswith("/app")


def test_incoming_signup_has_pending_claim_not_provisional_privilege(
    isolated_registration_db
):
    client = TestClient(app, follow_redirects=False)

    response = register(
        client,
        entry_path="incoming",
        student_id=""
    )

    assert response.status_code == 303

    with Session(isolated_registration_db) as db:
        user = db.exec(
            select(User).where(User.username == "alice")
        ).one()

        claim = db.exec(
            select(StudentApplication)
        ).one()

        assert claim.entry_path == "incoming"
        assert claim.claimed_student_id is None
        assert user.provisional == 0


def test_landlord_signup_creates_correct_role(
    isolated_registration_db
):
    client = TestClient(app, follow_redirects=False)

    response = register(
        client,
        role="landlord",
        entry_path="",
        student_id=""
    )

    assert response.status_code == 303

    with Session(isolated_registration_db) as db:
        user = db.exec(select(User)).one()

        assert user.role == "landlord"

        assert db.exec(
            select(StudentApplication)
        ).all() == []


def test_signup_rejects_self_assigned_admin(
    isolated_registration_db
):
    client = TestClient(app, follow_redirects=False)

    response = register(
        client,
        role="admin",
        entry_path="",
        student_id=""
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/register")

    with Session(isolated_registration_db) as db:
        assert db.exec(select(User)).all() == []


def test_signup_rejects_missing_student_id(
    isolated_registration_db
):
    client = TestClient(app, follow_redirects=False)

    response = register(client, student_id="")

    assert response.status_code == 303
    assert response.headers["location"].endswith("/register")

    with Session(isolated_registration_db) as db:
        assert db.exec(select(User)).all() == []


def test_signup_rejects_invalid_email(
    isolated_registration_db
):
    client = TestClient(app, follow_redirects=False)

    response = register(
        client,
        email="not-an-email"
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/register")

    with Session(isolated_registration_db) as db:
        assert db.exec(select(User)).all() == []


def test_signup_rejects_duplicate_username(
    isolated_registration_db
):
    client = TestClient(app, follow_redirects=False)

    assert register(client).status_code == 303

    duplicate = register(
        client,
        username="alice",
        email="alice2@example.com"
    )

    assert duplicate.status_code == 303
    assert duplicate.headers["location"].endswith("/register")

    with Session(isolated_registration_db) as db:
        assert len(db.exec(select(User)).all()) == 1
        assert len(
            db.exec(select(StudentApplication)).all()
        ) == 1


def test_service_rejects_untrusted_role(
    isolated_registration_db
):
    with Session(isolated_registration_db) as db:
        service = AuthService(UserRepository(db))

        with pytest.raises(ValueError):
            service.register_user(
                "admin2",
                "admin2@example.com",
                "password123",
                role="admin"
            )

        assert db.exec(select(User)).all() == []


def test_register_page_has_role_and_enrollment_controls():
    client = TestClient(app)

    response = client.get("/register")

    assert response.status_code == 200
    assert 'name="role"' in response.text
    assert 'value="landlord"' in response.text
    assert 'name="entry_path"' in response.text
    assert 'name="student_id"' in response.text
