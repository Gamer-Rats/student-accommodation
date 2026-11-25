
from fastapi import HTTPException, Request
from urllib.parse import urlsplit
from fastapi.responses import HTMLResponse

from app.dependencies.session import SessionDep
from app.dependencies.auth import AuthDep
from app.services.listings import (
    browse_for_students,
    get_student_listing,
    list_for_landlord,
)
from app.services.location_rules import (
    ALLOWED_AREAS,
    LOCATION_ERROR,
)
from .landlord_lifecycle import get_lifecycle_csrf_token
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


@router.get(
    "/app/landlord/rejections",
    response_class=HTMLResponse,
)
def landlord_rejections_view(
    request: Request,
    user: AuthDep,
):
    """Show rejected listings belonging to the logged-in landlord."""

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

    rejected = [
        listing
        for listing in result["listings"]
        if listing["status"] == "rejected"
    ]

    return templates.TemplateResponse(
        request=request,
        name="landlord-rejections.html",
        context={
            "user": user,
            "listings": rejected,
        },
    )


@router.get(
    "/app/landlord/listings",
    response_class=HTMLResponse,
)
def landlord_listings_view(
    request: Request,
    user: AuthDep,
):
    """Display all listings owned by the authenticated landlord."""

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

    landlord_listings = result["listings"]

    counts = {
        "total": len(landlord_listings),
        "pending": 0,
        "active": 0,
        "rejected": 0,
    }

    for listing in landlord_listings:
        listing_status = listing["status"]

        if listing_status in counts:
            counts[listing_status] += 1

    return templates.TemplateResponse(
        request=request,
        name="landlord-listings.html",
        context={
            "user": user,
            "listings": landlord_listings,
            "counts": counts,
            "csrf_token": get_lifecycle_csrf_token(request),
        },
    )


@router.get(
    "/app/listings/{listing_id}",
    response_class=HTMLResponse,
    name="student_listing_details_view",
)
def student_listing_details_view(
    request: Request,
    listing_id: int,
    user: AuthDep,
):
    """Display details of a student-accessible listing."""

    result = get_student_listing(user.id, listing_id)

    if not result["ok"]:
        error = result.get("error", "listing not found")

        if error in {
            "students only",
            "student eligibility required",
        }:
            raise HTTPException(
                status_code=403,
                detail=error,
            )

        raise HTTPException(
            status_code=404,
            detail="Listing not found",
        )

    listing = result["listing"]

    amenities = [
        amenity.strip()
        for amenity in (listing.get("amenities") or "").split(",")
        if amenity.strip()
    ]

    photo_urls = []
    photo_references = []

    for item in (listing.get("photos") or "").split(","):
        photo = item.strip()

        if not photo:
            continue

        parsed = urlsplit(photo)

        if (
            parsed.scheme.lower() in {"http", "https"}
            and parsed.netloc
        ):
            photo_urls.append(photo)
        else:
            photo_references.append(photo)

    return templates.TemplateResponse(
        request=request,
        name="student-listing-details.html",
        context={
            "user": user,
            "listing": listing,
            "amenities": amenities,
            "photo_urls": photo_urls,
            "photo_references": photo_references,
        },
    )
