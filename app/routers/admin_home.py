
"""Administrator pages and listing review actions."""

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


def _get_review_token(request: Request) -> str:
    """Create or reuse a CSRF token for admin forms."""

    token = request.session.get(ADMIN_REVIEW_CSRF_KEY)

    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[ADMIN_REVIEW_CSRF_KEY] = token

    return token


def _check_review_token(
    request: Request,
    submitted_token: str,
) -> None:
    """Reject requests with invalid security tokens."""

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


@router.get("/admin", response_class=HTMLResponse)
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
    action: str = Form(),
    csrf_token: str = Form(default=""),
    review_feedback: str = Form(default=""),
):
    """Apply administrator actions through authorized workflows."""

    _check_review_token(request, csrf_token)

    if action not in ADMIN_REVIEW_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail="Invalid review action",
        )

    # Task #49: Administrative hold management.
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
        # Existing State Pattern lifecycle actions.
        result = listings.transition(
            user.id,
            listing_id,
            action,
            review_feedback=(
                review_feedback
                if action == "reject"
                else None
            ),
        )

    if not result["ok"]:
        flash(
            request,
            result.get(
                "error",
                "Review action failed.",
            ),
            "danger",
        )

    elif action == "verify":
        flash(
            request,
            "Listing verified and approved successfully.",
            "success",
        )

    elif action == "reject":
        flash(
            request,
            "Listing rejected. The landlord can now view "
            "the administrator's feedback.",
            "success",
        )

    elif action == "provisionally_accept":
        flash(
            request,
            "Listing provisionally accepted. "
            "Final administrator verification is still required.",
            "success",
        )

    elif action == "force_deactivate":
        flash(
            request,
            "Listing forcibly deactivated and placed "
            "on administrative hold.",
            "success",
        )

    elif action == "release_admin_hold":
        flash(
            request,
            "Administrative hold released. "
            "The listing now requires reverification "
            "before it can be reactivated.",
            "success",
        )

    elif action == "complete_reverification":
        flash(
            request,
            "Listing reverification completed successfully. "
            "The landlord may now reactivate the listing.",
            "success",
        )

    return RedirectResponse(
        url=str(request.url_for("admin_listings_view")),
        status_code=status.HTTP_303_SEE_OTHER,
    )
