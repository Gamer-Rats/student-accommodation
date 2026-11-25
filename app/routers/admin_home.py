
"""Task #52: Administrator review validation and feedback."""

import secrets

from fastapi import Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.dependencies.auth import AdminDep
from app.services import listings
from app.services.admin_hold_policy import (
    release_admin_hold,
    complete_reverification,
)
from app.services.lifecycle import STATES
from app.services.location_rules import LOCATION_ERROR
from app.utilities.flash import flash

from . import router, templates


ADMIN_REVIEW_CSRF_KEY = "admin_review_csrf"

ADMIN_REVIEW_ACTIONS = {
    "verify",
    "reject",
    "provisionally_accept",
    "force_deactivate",
    "release_admin_hold",
    "complete_reverification",
}

MAX_REJECTION_FEEDBACK = 1000

SUCCESS_MESSAGES = {
    "verify": (
        "Listing verified and approved successfully."
    ),
    "reject": (
        "Listing rejected. The landlord can now view "
        "the administrator's feedback."
    ),
    "provisionally_accept": (
        "Listing provisionally accepted. "
        "Final administrator verification is still required."
    ),
    "force_deactivate": (
        "Listing forcibly deactivated and placed "
        "on administrative hold."
    ),
    "release_admin_hold": (
        "Administrative hold released. "
        "The listing now requires reverification "
        "before it can be reactivated."
    ),
    "complete_reverification": (
        "Listing reverification completed successfully. "
        "The landlord may now reactivate the listing."
    ),
}


def _get_review_token(request: Request) -> str:
    """Create or reuse a CSRF token for administrator forms."""

    token = request.session.get(ADMIN_REVIEW_CSRF_KEY)

    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[ADMIN_REVIEW_CSRF_KEY] = token

    return token


def _check_review_token(
    request: Request,
    submitted_token: str,
) -> None:
    """Reject missing or invalid form security tokens."""

    expected = request.session.get(ADMIN_REVIEW_CSRF_KEY)

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


def _review_redirect(request: Request):
    """Return to the administrator listing dashboard."""

    return RedirectResponse(
        url=str(request.url_for("admin_listings_view")),
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _safe_review_error(error: str | None) -> str:
    """Convert known service errors to safe browser messages."""

    if error == "rejection feedback is required":
        return "rejection feedback is required"

    if error == "rejection feedback is too long":
        return (
            "Rejection feedback must not exceed "
            "1000 characters."
        )

    if error == LOCATION_ERROR:
        return (
            "Accommodation location must be "
            "St. Augustine or Mount Hope."
        )

    if error == "price must be positive":
        return "Monthly rent must be greater than zero."

    if error and error.startswith("Cannot perform"):
        return (
            "Cannot perform this action in the "
            "listing's current state."
        )

    known_errors = {
        "Only inactive listings can have "
        "administrative holds released": (
            "Only inactive listings can have "
            "administrative holds released."
        ),
        "listing is not on administrative hold": (
            "This listing is not on administrative hold."
        ),
        "Only inactive listings can complete "
        "this reverification workflow": (
            "Only inactive listings can be reverified."
        ),
        "Release the administrative hold "
        "before completing reverification": (
            "Release the administrative hold "
            "before completing reverification."
        ),
        "listing does not require reverification": (
            "This listing does not require reverification."
        ),
        "title is required": (
            "Listing title is required."
        ),
        "contact_phone is required": (
            "Contact phone number is required."
        ),
        "contact_email is required": (
            "Contact email address is required."
        ),
    }

    return known_errors.get(
        error,
        "Unable to complete this action. "
        "Review the listing status and try again.",
    )


@router.get(
    "/admin",
    response_class=HTMLResponse,
)
async def admin_home_view(
    request: Request,
    user: AdminDep,
):
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "user": user,
        },
    )


@router.get(
    "/admin/listings",
    response_class=HTMLResponse,
)
def admin_listings_view(
    request: Request,
    user: AdminDep,
    status: str | None = None,
):
    return templates.TemplateResponse(
        request=request,
        name="admin-listings.html",
        context={
            "user": user,
            "listings": listings.list_all(status=status),
            "states": STATES,
            "selected_status": status,
            "csrf_token": _get_review_token(request),
        },
    )


@router.post(
    "/admin/listings/{listing_id}/review",
    name="admin_review_action",
)
def admin_review_action(
    request: Request,
    listing_id: int,
    user: AdminDep,
    action: str = Form(default=""),
    csrf_token: str = Form(default=""),
    review_feedback: str = Form(default=""),
):
    """Validate and perform administrator listing actions."""

    # AdminDep enforces administrator authorization.
    # Check CSRF before processing the submitted action.
    _check_review_token(request, csrf_token)

    if action not in ADMIN_REVIEW_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail="Invalid review action",
        )

    feedback = review_feedback.strip()

    # Rejection requires meaningful feedback.
    if action == "reject":
        if not feedback:
            flash(
                request,
                "rejection feedback is required",
                "danger",
            )
            return _review_redirect(request)

        if len(feedback) > MAX_REJECTION_FEEDBACK:
            flash(
                request,
                "Rejection feedback must not exceed "
                "1000 characters.",
                "danger",
            )
            return _review_redirect(request)

    elif feedback:
        # Feedback must not accompany unrelated actions.
        raise HTTPException(
            status_code=400,
            detail="Feedback is only allowed when rejecting.",
        )

    # Preserve the existing administrator hold policies.
    if action == "release_admin_hold":
        result = release_admin_hold(
            user.id,
            listing_id,
        )

    elif action == "complete_reverification":
        result = complete_reverification(
            user.id,
            listing_id,
        )

    else:
        result = listings.transition(
            user.id,
            listing_id,
            action,
            review_feedback=(
                feedback if action == "reject" else None
            ),
        )

    if not result["ok"]:
        error = result.get("error")

        if error == "listing not found":
            raise HTTPException(
                status_code=404,
                detail="Listing not found",
            )

        if error == "admin only":
            raise HTTPException(
                status_code=403,
                detail="Access denied",
            )

        # Never expose unexpected internal service errors.
        flash(
            request,
            _safe_review_error(error),
            "danger",
        )

        return _review_redirect(request)

    # Confirm success only when the service succeeds.
    flash(
        request,
        SUCCESS_MESSAGES[action],
        "success",
    )

    return _review_redirect(request)
