
"""Task #45: Landlord inbox for student accommodation inquiries."""

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import select

from app.dependencies.auth import AuthDep
from app.dependencies.session import SessionDep
from app.models.listing import Listing
from app.models.message import Message
from app.models.user import User

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

    # Only retrieve messages associated with listings
    # belonging to the authenticated landlord.
    statement = (
        select(Message, Listing, User)
        .join(
            Listing,
            Message.listing_id == Listing.id,
        )
        .outerjoin(
            User,
            Message.student_id == User.id,
        )
        .where(
            Listing.landlord_id == user.id,
        )
        .order_by(
            Message.created_at.desc(),
            Message.id.desc(),
        )
    )

    rows = db.exec(statement).all()

    inbox_messages = []

    for message, listing, student in rows:

        if student is not None:
            student_name = (
                student.display_name
                or student.username
            )
            student_username = student.username

        else:
            student_name = "Student"
            student_username = "Unknown"

        inbox_messages.append(
            {
                "id": message.id,
                "listing_id": listing.id,
                "listing_title": listing.title,
                "student_id": message.student_id,
                "student_name": student_name,
                "student_username": student_username,
                "body": message.body,
                "created_at": message.created_at,
            }
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

