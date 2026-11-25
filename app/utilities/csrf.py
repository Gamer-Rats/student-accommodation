
"""Reusable CSRF protection for browser forms."""

import secrets

from fastapi import HTTPException, Request, status


CSRF_SESSION_KEY = "browser_csrf_token"


def get_csrf_token(request: Request) -> str:
    """Create or retrieve a CSRF token for the browser session."""

    token = request.session.get(CSRF_SESSION_KEY)

    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token

    return token


def validate_csrf_token(
    request: Request,
    submitted_token: str,
) -> None:
    """Reject requests with missing or invalid CSRF tokens."""

    expected = request.session.get(CSRF_SESSION_KEY)

    if (
        not isinstance(expected, str)
        or not expected
        or not isinstance(submitted_token, str)
        or not secrets.compare_digest(
            expected,
            submitted_token,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing form security token",
        )


def rotate_csrf_token(request: Request) -> str:
    """Generate a fresh CSRF token for the session."""

    token = secrets.token_urlsafe(32)

    request.session[CSRF_SESSION_KEY] = token

    return token
