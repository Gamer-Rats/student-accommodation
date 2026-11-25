
"""Task #43: Landlord listing activation and deactivation."""

import secrets

from fastapi import Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.dependencies.auth import AuthDep
from app.services import listings
from app.utilities.flash import flash

from . import router


CSRF_SESSION_KEY = "landlord_lifecycle_csrf"

ALLOWED_ACTIONS = {"activate", "deactivate"}


def get_lifecycle_csrf_token(request: Request) -> str:
    """Create or retrieve the security token for lifecycle forms."""

    token = request.session.get(CSRF_SESSION_KEY)

    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token

    return token


def check_lifecycle_csrf_token(
    request: Request,
    submitted_token: str,
) -> None:
    """Reject requests with missing or invalid CSRF tokens."""

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
    "/app/landlord/listings/{listing_id}/lifecycle",
    name="landlord_lifecycle_action",
)
def landlord_lifecycle_action(
    request: Request,
    listing_id: int,
    user: AuthDep,
    action: str = Form(),
    csrf_token: str = Form(default=""),
):
    """Activate or deactivate a listing owned by the landlord."""

    if user.role != "landlord":
        raise HTTPException(
            status_code=403,
            detail="Landlords only",
        )

    check_lifecycle_csrf_token(request, csrf_token)

    if action not in ALLOWED_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail="Invalid landlord lifecycle action",
        )

    # Confirm that the listing belongs to the logged-in landlord.
    result = listings.list_for_landlord(user.id)

    if not result["ok"]:
        raise HTTPException(
            status_code=403,
            detail=result.get("error", "Access denied"),
        )

    owned_ids = {
        listing["id"]
        for listing in result["listings"]
    }

    if listing_id not in owned_ids:
        raise HTTPException(
            status_code=404,
            detail="Listing not found",
        )

    # The existing service enforces state transitions,
    # ownership and administrative restrictions.
    result = listings.transition(
        user.id,
        listing_id,
        action,
    )

    if not result["ok"]:
        flash(
            request,
            result.get("error", "Unable to update listing."),
            "danger",
        )

    elif action == "activate":
        flash(
            request,
            "Listing activated successfully. "
            "Eligible students can now view it.",
            "success",
        )

    else:
        flash(
            request,
            "Listing deactivated successfully. "
            "It is no longer visible to students.",
            "success",
        )

    return RedirectResponse(
        url=str(request.url_for("landlord_listings_view")),
        status_code=status.HTTP_303_SEE_OTHER,
    )
