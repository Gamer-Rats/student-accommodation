
"""Task #45: Landlord inbox for student accommodation inquiries."""

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

from app.dependencies.auth import AuthDep
from app.dependencies.session import SessionDep
from app.services import listings

from . import router, templates


@router.get(
    "/app/landlord/inbox",
    response_class=HTMLResponse,
    name="landlord_inbox_view",
)
def landlord_inbox_view(
    request: Request,
    user: AuthDep,
    db: SessionDep,
):
    """Display student messages for the logged-in landlord."""

    if user.role != "landlord":
        raise HTTPException(
            status_code=403,
            detail="Landlords only",
        )

    inbox_messages = listings.get_landlord_inbox(
        user.id,
        db,
    )

    return templates.TemplateResponse(
        request=request,
        name="landlord-inbox.html",
        context={
            "user": user,
            "messages": inbox_messages,
            "message_count": len(inbox_messages),
        },
    )

