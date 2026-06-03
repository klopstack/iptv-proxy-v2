"""Tests for stateless Flask configuration (no SECRET_KEY / session cookies)."""

from services.flask_session import NullSessionInterface


def test_app_runs_without_secret_key(client):
    """Requests succeed without SECRET_KEY when Flask sessions are disabled."""
    response = client.get("/")
    assert response.status_code == 200


def test_null_session_interface_configured(app):
    """App uses NullSessionInterface instead of signed cookie sessions."""
    assert isinstance(app.session_interface, NullSessionInterface)
    assert not app.config.get("SECRET_KEY")


def test_no_session_cookie_set(client):
    """Responses do not set a Flask session cookie."""
    response = client.get("/")
    cookie_names = {key.split("=", 1)[0].strip().lower() for key in response.headers.getlist("Set-Cookie")}
    assert "session" not in cookie_names
