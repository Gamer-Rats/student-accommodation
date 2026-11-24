"""Shallow scenario smoke tests — intentionally weak."""

from fastapi.testclient import TestClient

from app.main import app
from app.seed import seed


def setup_module() -> None:
    seed(reset=True)


client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["scenario"] == "student-accommodation"


def test_login_admin():
    r = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-dev"},
    )
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "admin"
    assert "password" not in r.json()["user"]


def test_student_browse():
    login = client.post(
        "/api/auth/login",
        json={"email": "student@example.com", "password": "stud-dev"},
    )
    uid = login.json()["user"]["id"]
    r = client.get("/api/student/listings", headers={"X-User-Id": str(uid)})
    assert r.status_code == 200
    assert isinstance(r.json()["listings"], list)


def test_student_can_follow_listings_link_after_browser_sign_in():
    with TestClient(app, base_url="http://testserver/local", root_path="/local") as browser:
        home = browser.post(
            "/login", data={"username": "student", "password": "stud-dev"}
        )
        assert home.url.path == "/local/app"
        listings_url = "http://testserver/local/app/listings"
        assert f'href="{listings_url}"' in home.text

        response = browser.get(listings_url)
        filtered = browser.get(listings_url, params={"max_price": 3000})
        api_response = browser.get("/api/student/listings")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Verified Active Flat" in response.text
    assert filtered.status_code == 200
    assert "No student listings are available" in filtered.text
    assert api_response.status_code == 200
    assert isinstance(api_response.json()["listings"], list)


def test_admin_can_follow_and_filter_listings_after_browser_sign_in():
    with TestClient(app) as browser:
        home = browser.post(
            "/login", data={"username": "admin", "password": "admin-dev"}
        )
        assert home.url.path == "/admin"
        listings_url = "http://testserver/admin/listings"
        assert f'href="{listings_url}"' in home.text

        response = browser.get(listings_url)
        pending = browser.get(listings_url, params={"status": "pending"})
        api_response = browser.get("/api/admin/listings")

        assert response.status_code == 200
        assert "Verified Active Flat" in response.text
        assert "Pending Unit" in response.text
        assert pending.status_code == 200
        assert "Pending Unit" in pending.text
        assert "Verified Active Flat" not in pending.text
        assert api_response.status_code == 200
        assert len(api_response.json()["listings"]) == 2

        browser.get("/logout")
        assert browser.get(listings_url).status_code == 401
        unauthorized = browser.get("/api/admin/listings")
        assert unauthorized.status_code == 401
        assert unauthorized.json() == {"detail": "X-User-Id header required"}


def test_student_cannot_open_admin_listings():
    with TestClient(app) as browser:
        browser.post("/login", data={"username": "student", "password": "stud-dev"})
        assert browser.get("/admin/listings").status_code == 401
        assert browser.get("/api/admin/listings").status_code == 403
