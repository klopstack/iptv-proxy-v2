"""Flask session configuration for proxy-auth deployments.

Admin authentication is handled by Traefik + Authentik (see docs/DEPLOYMENT.md).
The app does not use Flask session cookies, flash messages, or CSRF tokens, so
SECRET_KEY is not required for security.
"""

from __future__ import annotations

from flask import Flask
from flask.sessions import SessionInterface


class NullSessionInterface(SessionInterface):
    """Disable signed session cookies — no SECRET_KEY needed."""

    def open_session(self, app: Flask, request):  # noqa: ARG002
        return self.make_null_session(app)

    def save_session(self, app: Flask, session, response):  # noqa: ARG002
        pass


def disable_flask_sessions(app: Flask) -> None:
    """Use stateless requests; auth is external (Traefik + Authentik / Xtream)."""
    app.session_interface = NullSessionInterface()
