
"""Task #34: Landlord listing editing and resubmission pages."""

import secrets

from fastapi import Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.dependencies.auth import AuthDep
from app.services import listings
from app.services.location_rules import ALLOWED_AREAS
from app.utilities.flash import flash
from . import router, templates


EDITABLE_STATUSES = {"pending", "rejected"}
CSRF_SESSION_KEY = "landlord_edit_csrf"


def _require_landlord(user):
    if user.role != "landlord":
        raise HTTPException(
            status_code=403,
            detail="Landlords only",
        )


def _owned_listing(user, listing_id: int):
    """Only return a listing belonging to this landlord."""

    _require_landlord(user)

    result = listings.list_for_landlord(user.id)

    if not result["ok"]:
        raise HTTPException(
            status_code=403,
            detail=result["error"],
        )

    for item in result["listings"]:
        if item["id"] == listing_id:
            return item

    # Do not reveal whether another landlord owns the ID.
    raise HTTPException(
        status_code=404,
        detail="Listing not found",
    )


def _get_csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)

    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token

    return token


def _check_csrf(request: Request, submitted_token: str):
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
    csrf_token: str = Form(),
    title: str = Form(),
    area: str = Form(),
    price: str = Form(),
    amenities: str = Form(default=""),
    contact_phone: str = Form(),
    contact_email: str = Form(),
    photos: str = Form(default=""),
):
    _check_csrf(request, csrf_token)

    listing = _owned_listing(user, listing_id)

    if listing["status"] not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="This listing cannot currently be edited",
        )

    edit_url = request.url_for(
        "landlord_edit_view",
        listing_id=listing_id,
    )

    try:
        numeric_price = int(price)
    except ValueError:
        flash(
            request,
            "Price must be a whole number.",
            "danger",
        )
        return RedirectResponse(
            url=str(edit_url),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    result = listings.update_listing(
        user.id,
        listing_id,
        title=title,
        area=area,
        price=numeric_price,
        amenities=amenities,
        contact_phone=contact_phone,
        contact_email=contact_email,
        photos=photos,
    )

    if not result["ok"]:
        flash(
            request,
            result.get("error", "Could not save changes."),
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
    csrf_token: str = Form(),
):
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
            result.get("error", "Resubmission failed."),
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
