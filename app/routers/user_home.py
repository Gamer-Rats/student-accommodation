
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

from app.dependencies.session import SessionDep
from app.dependencies.auth import AuthDep
from app.services.listings import (
    browse_for_students,
    list_for_landlord,
)
from app.services.location_rules import (
    ALLOWED_AREAS,
    LOCATION_ERROR,
)
from . import router, templates


@router.get("/app", response_class=HTMLResponse)
async def user_home_view(
    request: Request,
    user: AuthDep,
    db: SessionDep,
):
    return templates.TemplateResponse(
        request=request,
        name="app.html",
        context={
            "user": user,
        },
    )


@router.get("/app/listings", response_class=HTMLResponse)
def student_listings_view(
    request: Request,
    user: AuthDep,
    area: str = "",
    max_price: str = "",
    amenity: str = "",
):
    try:
        price_limit = int(max_price) if max_price else None

    except ValueError:
        result = {
            "ok": False,
            "error": "Maximum price must be a whole number.",
        }
        status_code = 400

    else:
        result = browse_for_students(
            user.id,
            area=area or None,
            max_price=price_limit,
            amenity=amenity,
        )

        status_code = 200 if result["ok"] else (
            400 if result.get("error") == LOCATION_ERROR else 403
        )

    return templates.TemplateResponse(
        request=request,
        name="student-listings.html",
        context={
            "user": user,
            "listings": result.get("listings", []),
            "error": result.get("error"),
            "areas": sorted(ALLOWED_AREAS),
            "selected_area": area,
            "max_price": max_price,
            "amenity": amenity,
        },
        status_code=status_code,
    )


@router.get("/app/landlord/listings/data")
def landlord_listings_data(user: AuthDep):
    """Authenticated listing data for the landlord dashboard."""

    if user.role != "landlord":
        raise HTTPException(
            status_code=403,
            detail="landlords only",
        )

    result = list_for_landlord(user.id)

    if not result["ok"]:
        raise HTTPException(
            status_code=403,
            detail=result["error"],
        )

    return result
