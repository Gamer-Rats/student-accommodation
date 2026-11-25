
"""Task #44: Student accommodation messaging form."""

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
    """Send a message to the landlord of an available listing."""

    if user.role != "student":
        raise HTTPException(
            status_code=403,
            detail="Students only",
        )

    check_message_csrf_token(
        request,
        csrf_token,
    )

    listing_url = request.url_for(
        "student_listing_details_view",
        listing_id=listing_id,
    )

    browse_url = request.url_for(
        "student_listings_view"
    )

    cleaned_body = body.strip()

    if not cleaned_body:
        flash(
            request,
            "Please enter a message before sending.",
            "danger",
        )

        return RedirectResponse(
            url=str(listing_url),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if len(cleaned_body) > MAX_MESSAGE_LENGTH:
        flash(
            request,
            "Your message cannot exceed 2000 characters.",
            "danger",
        )

        return RedirectResponse(
            url=str(listing_url),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Reuse the existing messaging service.
    # The service checks student eligibility and listing availability.
    result = listings.send_message(
        student_id=user.id,
        listing_id=listing_id,
        body=cleaned_body,
    )

    if not result["ok"]:
        error = result.get(
            "error",
            "Unable to send your message.",
        )

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

            return RedirectResponse(
                url=str(browse_url),
                status_code=status.HTTP_303_SEE_OTHER,
            )

        flash(
            request,
            error,
            "danger",
        )

        return RedirectResponse(
            url=str(listing_url),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    flash(
        request,
        "Your message has been sent successfully "
        "to the landlord.",
        "success",
    )

    return RedirectResponse(
        url=str(listing_url),
        status_code=status.HTTP_303_SEE_OTHER,
    )
