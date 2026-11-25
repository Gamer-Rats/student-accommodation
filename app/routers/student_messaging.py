
"""Task #52: Student messaging validation and user feedback."""

import secrets

from fastapi import Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.dependencies.auth import AuthDep
from app.services import listings
from app.utilities.flash import flash

from . import router


CSRF_SESSION_KEY = "student_message_csrf"
MAX_MESSAGE_LENGTH = 2000


def get_message_csrf_token(request: Request) -> str:
    """Create or retrieve the student's message form token."""

    token = request.session.get(CSRF_SESSION_KEY)

    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token

    return token


def check_message_csrf_token(
    request: Request,
    submitted_token: str,
) -> None:
    """Reject forms with invalid or missing security tokens."""

    expected = request.session.get(CSRF_SESSION_KEY)

    if (
        not isinstance(expected, str)
        or not expected
        or not secrets.compare_digest(
            expected,
            submitted_token,
        )
    ):
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing form security token",
        )


def validate_message_body(body: str) -> dict:
    """Validate the message before calling the service."""

    cleaned_body = body.strip()

    if not cleaned_body:
        return {
            "ok": False,
            "error": "Please enter a message before sending.",
        }

    if len(cleaned_body) > MAX_MESSAGE_LENGTH:
        return {
            "ok": False,
            "error": (
                "Your message cannot exceed "
                "2000 characters."
            ),
        }

    return {
        "ok": True,
        "body": cleaned_body,
    }


def _redirect(request: Request, route: str, **params):
    """Redirect after browser form processing."""

    return RedirectResponse(
        url=str(request.url_for(route, **params)),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/app/listings/{listing_id}/message",
    name="student_send_message_action",
)
def student_send_message_action(
    request: Request,
    listing_id: int,
    user: AuthDep,
    body: str = Form(default=""),
    csrf_token: str = Form(default=""),
):
    """Validate and send a student accommodation inquiry."""

    # Authorization.
    if user.role != "student":
        raise HTTPException(
            status_code=403,
            detail="Students only",
        )

    # CSRF protection.
    check_message_csrf_token(
        request,
        csrf_token,
    )

    # Validate input before any message is created.
    validation = validate_message_body(body)

    if not validation["ok"]:
        flash(
            request,
            validation["error"],
            "danger",
        )

        return _redirect(
            request,
            "student_listing_details_view",
            listing_id=listing_id,
        )

    result = listings.send_message(
        student_id=user.id,
        listing_id=listing_id,
        body=validation["body"],
    )

    if not result["ok"]:
        error = result.get("error")

        if error in {
            "listing not found",
            "listing not available",
        }:
            flash(
                request,
                "This accommodation is no longer available "
                "for messaging.",
                "danger",
            )

            return _redirect(
                request,
                "student_listings_view",
            )

        if error == "student eligibility required":
            flash(
                request,
                "Your student account is not currently "
                "eligible to send messages.",
                "danger",
            )

        else:
            # Do not show raw internal service errors.
            flash(
                request,
                "Unable to send your message. "
                "Please try again.",
                "danger",
            )

        return _redirect(
            request,
            "student_listing_details_view",
            listing_id=listing_id,
        )

    # Display success only after the service confirms saving.
    flash(
        request,
        "Your message has been sent successfully "
        "to the landlord.",
        "success",
    )

    return _redirect(
        request,
        "student_listing_details_view",
        listing_id=listing_id,
    )
