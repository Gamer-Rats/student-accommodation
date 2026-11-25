
"""Task #41: Tests for the administrator-only user directory."""

import pytest

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.database import get_session
from app.main import app
from app.models.user import User
from app.utilities.security import create_access_token


@pytest.fixture
def directory_client(test_session):
    """Create test accounts in an isolated database."""

    admin = User(
        username="directory_admin",
        email="directory_admin@example.com",
        password="test-password",
        role="admin",
    )

    student = User(
        username="directory_student",
        email="directory_student@example.com",
        password="test-password",
        role="student",
    )

    test_session.add(admin)
    test_session.add(student)
    test_session.commit()

    test_session.refresh(admin)
    test_session.refresh(student)

    def override_session():
        with Session(test_session.bind) as session:
            yield session

    previous_override = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = override_session

    client = TestClient(app)

    try:
        yield client, admin.id, student.id
    finally:
        client.close()

        if previous_override is None:
            app.dependency_overrides.pop(get_session, None)
        else:
            app.dependency_overrides[get_session] = previous_override


def sign_in_as(client, user_id, role):
    """Authenticate a test user using a signed access token."""

    token = create_access_token(
        {
            "sub": str(user_id),
            "role": role,
        }
    )

    client.cookies.set("access_token", token)


def test_unauthenticated_user_cannot_view_directory(
    directory_client,
):
    client, _, _ = directory_client

    response = client.get("/api/users")

    assert response.status_code == 401


def test_student_cannot_view_directory(
    directory_client,
):
    client, _, student_id = directory_client

    sign_in_as(client, student_id, "student")

    response = client.get("/api/users")

    assert response.status_code == 403
    assert response.json()["detail"] == "Administrators only"


def test_administrator_can_view_directory(
    directory_client,
):
    client, admin_id, _ = directory_client

    sign_in_as(client, admin_id, "admin")

    response = client.get("/api/users")

    assert response.status_code == 200

    users = response.json()

    assert len(users) == 2

    usernames = {user["username"] for user in users}

    assert usernames == {
        "directory_admin",
        "directory_student",
    }

    for user in users:
        assert set(user.keys()) == {
            "id",
            "username",
            "email",
        }

        assert "password" not in user


def test_forged_admin_role_does_not_grant_access(
    directory_client,
):
    client, _, student_id = directory_client

    # The signed token claims admin privileges,
    # but the real account is a student.
    sign_in_as(client, student_id, "admin")

    response = client.get("/api/users")

    assert response.status_code == 403
