
"""Task #42: Landlord accommodation listing submission."""

import secrets

from fastapi import Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.dependencies.auth import AuthDep
from app.services import listings
from app.services.location_rules import ALLOWED_AREAS
from app.utilities.flash import flash

from . import router, templates


CSRF_SESSION_KEY = "landlord_submit_csrf"


def _require_landlord(user):
    """Only authenticated landlords may submit listings."""

    if user.role != "landlord":
        raise HTTPException(
            status_code=403,
            detail="Landlords only",
        )


def _get_csrf_token(request: Request) -> str:
    """Create or reuse a security token for the form."""

    token = request.session.get(CSRF_SESSION_KEY)

    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token

    return token


def _check_csrf_token(
    request: Request,
    submitted_token: str,
):
    """Reject requests with invalid security tokens."""

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
    """Show the accommodation submission form."""

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
    title: str = Form(),
    area: str = Form(),
    price: str = Form(),
    amenities: str = Form(default=""),
    contact_phone: str = Form(),
    contact_email: str = Form(),
    photos: str = Form(default=""),
):
    """Validate and submit an accommodation listing."""

    _require_landlord(user)
    _check_csrf_token(request, csrf_token)

    form_url = request.url_for("landlord_submit_view")

    title = title.strip()
    contact_phone = contact_phone.strip()
    contact_email = contact_email.strip()

    if not title or len(title) > 200:
        flash(
            request,
            "Listing title must contain 1 to 200 characters.",
            "danger",
        )

        return RedirectResponse(
            url=str(form_url),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if not contact_phone or not contact_email:
        flash(
            request,
            "Contact phone and email are required.",
            "danger",
        )

        return RedirectResponse(
            url=str(form_url),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        numeric_price = int(price)

    except ValueError:
        flash(
            request,
            "Monthly rent must be a whole number.",
            "danger",
        )

        return RedirectResponse(
            url=str(form_url),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if numeric_price <= 0:
        flash(
            request,
            "Monthly rent must be greater than zero.",
            "danger",
        )

        return RedirectResponse(
            url=str(form_url),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    result = listings.submit_listing(
        user.id,
        title=title,
        area=area,
        price=numeric_price,
        amenities=amenities.strip(),
        contact_phone=contact_phone,
        contact_email=contact_email,
        photos=photos.strip(),
    )

    if not result["ok"]:
        flash(
            request,
            result.get(
                "error",
                "Unable to submit accommodation listing.",
            ),
            "danger",
        )

        return RedirectResponse(
            url=str(form_url),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    flash(
        request,
        "Accommodation listing submitted successfully. "
        "It is now Pending administrator review.",
        "success",
    )

    return RedirectResponse(
        url=str(request.url_for("landlord_listings_view")),
        status_code=status.HTTP_303_SEE_OTHER,
    )
