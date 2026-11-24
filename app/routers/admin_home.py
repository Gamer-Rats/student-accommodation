from fastapi import Request
from fastapi.responses import HTMLResponse
from app.dependencies.auth import AdminDep
from app.services.lifecycle import STATES
from app.services.listings import list_all
from . import router, templates


@router.get("/admin", response_class=HTMLResponse)
async def admin_home_view(
    request: Request,
    user: AdminDep,
):
    return templates.TemplateResponse(
        request=request, 
        name="admin.html",
        context={
            "user": user
        }
    )


@router.get("/admin/listings", response_class=HTMLResponse)
def admin_listings_view(
    request: Request, user: AdminDep, status: str | None = None
):
    return templates.TemplateResponse(
        request=request,
        name="admin-listings.html",
        context={
            "user": user,
            "listings": list_all(status=status),
            "states": STATES,
            "selected_status": status,
        },
    )
