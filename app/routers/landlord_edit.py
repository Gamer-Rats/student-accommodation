
"""Task #52: Validated landlord listing editing and resubmission."""

import secrets

from fastapi import Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.dependencies.auth import AuthDep
from app.services import listings
from app.services.location_rules import ALLOWED_AREAS
from app.utilities.browser_validation import validate_listing_form
from app.utilities.flash import flash

from . import router, templates


EDITABLE_STATUSES = {"pending", "rejected"}
CSRF_SESSION_KEY = "landlord_edit_csrf"


def _require_landlord(user):
    """Allow only landlords to access editing workflows."""

    if user.role != "landlord":
        raise HTTPException(
            status_code=403,
            detail="Landlords only",
        )


def _owned_listing(user, listing_id: int):
    """Retrieve a listing belonging to the authenticated landlord."""

    _require_landlord(user)

    result = listings.list_for_landlord(user.id)

    if not result["ok"]:
        raise HTTPException(
            status_code=403,
            detail="Access denied",
        )

    for item in result["listings"]:
        if item["id"] == listing_id:
            return item

    # Hide whether another landlord owns this listing.
    raise HTTPException(
        status_code=404,
        detail="Listing not found",
    )


def _get_csrf_token(request: Request) -> str:
    """Create or retrieve the editing security token."""

    token = request.session.get(CSRF_SESSION_KEY)

    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token

    return token


def _check_csrf(request: Request, submitted_token: str):
    """Reject missing or invalid CSRF tokens."""

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


@router.get(
    "/app/landlord/listings/{listing_id}/edit",
    response_class=HTMLResponse,
    name="landlord_edit_view",
)
def landlord_edit_view(
    request: Request,
    listing_id: int,
    user: AuthDep,
):
    """Display the editing form for an owned, editable listing."""

    listing = _owned_listing(user, listing_id)

    if listing["status"] not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="This listing cannot currently be edited",
        )

    return templates.TemplateResponse(
        request=request,
        name="landlord-edit.html",
        context={
            "user": user,
            "listing": listing,
            "areas": sorted(ALLOWED_AREAS),
            "csrf_token": _get_csrf_token(request),
        },
    )


@router.post(
    "/app/landlord/listings/{listing_id}/edit",
    name="landlord_edit_action",
)
def landlord_edit_action(
    request: Request,
    listing_id: int,
    user: AuthDep,
    csrf_token: str = Form(default=""),
    title: str = Form(default=""),
    area: str = Form(default=""),
    price: str = Form(default=""),
    amenities: str = Form(default=""),
    contact_phone: str = Form(default=""),
    contact_email: str = Form(default=""),
    photos: str = Form(default=""),
):
    """Validate and save changes without bypassing lifecycle rules."""

    # Preserve authorization and ownership restrictions.
    _require_landlord(user)

    # Preserve CSRF protection.
    _check_csrf(request, csrf_token)

    listing = _owned_listing(user, listing_id)

    # Only pending and rejected listings may be edited.
    if listing["status"] not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="This listing cannot currently be edited",
        )

    edit_url = request.url_for(
        "landlord_edit_view",
        listing_id=listing_id,
    )

    # Use the same validation rules as listing submissions.
    validation = validate_listing_form(
        title=title,
        area=area,
        price=price,
        amenities=amenities,
        contact_phone=contact_phone,
        contact_email=contact_email,
        photos=photos,
    )

    if not validation["ok"]:
        flash(
            request,
            validation["error"],
            "danger",
        )

        return RedirectResponse(
            url=str(edit_url),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # No database update occurs before validation succeeds.
    clean_data = validation["data"]

    result = listings.update_listing(
        user.id,
        listing_id,
        **clean_data,
    )

    if not result["ok"]:
        flash(
            request,
            "Unable to save listing changes. Please try again.",
            "danger",
        )
    else:
        flash(
            request,
            "Listing details updated successfully.",
            "success",
        )

    return RedirectResponse(
        url=str(edit_url),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/app/landlord/listings/{listing_id}/resubmit",
    name="landlord_resubmit_action",
)
def landlord_resubmit_action(
    request: Request,
    listing_id: int,
    user: AuthDep,
    csrf_token: str = Form(default=""),
):
    """Resubmit a rejected listing for administrator review."""

    _require_landlord(user)
    _check_csrf(request, csrf_token)

    listing = _owned_listing(user, listing_id)

    if listing["status"] != "rejected":
        raise HTTPException(
            status_code=409,
            detail="Only rejected listings can be resubmitted",
        )

    result = listings.transition(
        user.id,
        listing_id,
        "resubmit",
    )

    if not result["ok"]:
        flash(
            request,
            "Unable to resubmit this listing. Please try again.",
            "danger",
        )

        destination = request.url_for(
            "landlord_edit_view",
            listing_id=listing_id,
        )
    else:
        flash(
            request,
            "Listing resubmitted. It is now Pending administrator review.",
            "success",
        )

        destination = request.url_for("user_home_view")

    return RedirectResponse(
        url=str(destination),
        status_code=status.HTTP_303_SEE_OTHER,
    )
