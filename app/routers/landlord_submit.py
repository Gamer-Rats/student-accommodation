
"""Task #52: Validated landlord listing submission."""

import secrets

from fastapi import Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.dependencies.auth import AuthDep
from app.services import listings
from app.services.location_rules import ALLOWED_AREAS
from app.utilities.flash import flash
from app.utilities.browser_validation import (
    validate_listing_form,
)

from . import router, templates


CSRF_SESSION_KEY = "landlord_submit_csrf"


def _require_landlord(user):
    """Only landlords may submit listings."""

    if user.role != "landlord":
        raise HTTPException(
            status_code=403,
            detail="Landlords only",
        )


def _get_csrf_token(request: Request) -> str:
    """Create or retrieve the form security token."""

    token = request.session.get(CSRF_SESSION_KEY)

    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token

    return token


def _check_csrf_token(
    request: Request,
    submitted_token: str,
):
    """Reject missing or invalid security tokens."""

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
    "/app/landlord/listings/new",
    response_class=HTMLResponse,
    name="landlord_submit_view",
)
def landlord_submit_view(
    request: Request,
    user: AuthDep,
):
    """Display the listing submission form."""

    _require_landlord(user)

    return templates.TemplateResponse(
        request=request,
        name="landlord-submit.html",
        context={
            "user": user,
            "areas": sorted(ALLOWED_AREAS),
            "csrf_token": _get_csrf_token(request),
        },
    )


@router.post(
    "/app/landlord/listings/new",
    name="landlord_submit_action",
)
def landlord_submit_action(
    request: Request,
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
    """Validate and submit a landlord accommodation listing."""

    # Authorization is always checked first.
    _require_landlord(user)

    # Preserve existing CSRF protection.
    _check_csrf_token(request, csrf_token)

    form_url = request.url_for("landlord_submit_view")

    # Shared validation.
    validation = validate_listing_form(
        title=title,
        area=area,
        price=price,
        amenities=amenities,
        contact_phone=contact_phone,
        contact_email=contact_email,
        photos=photos,
    )

    # Stop before any database operation if invalid.
    if not validation["ok"]:
        flash(
            request,
            validation["error"],
            "danger",
        )

        return RedirectResponse(
            url=str(form_url),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Validated, normalized values only.
    clean_data = validation["data"]

    result = listings.submit_listing(
        user.id,
        **clean_data,
    )

    if not result["ok"]:
        # Avoid exposing internal service details.
        flash(
            request,
            (
                "Unable to submit accommodation listing. "
                "Please review your details and try again."
            ),
            "danger",
        )

        return RedirectResponse(
            url=str(form_url),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Success feedback is shown only after saving.
    flash(
        request,
        "Accommodation listing submitted successfully. "
        "It is now Pending administrator review.",
        "success",
    )

    return RedirectResponse(
        url=str(
            request.url_for("landlord_listings_view")
        ),
        status_code=status.HTTP_303_SEE_OTHER,
    )
