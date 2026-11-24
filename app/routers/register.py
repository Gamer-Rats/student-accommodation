
"""Public student / landlord account registration."""

import logging

from fastapi import Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.dependencies import SessionDep
from app.repositories.user import UserRepository
from app.services.auth_service import AuthService
from app.utilities.flash import flash
from . import router, templates


logger = logging.getLogger(__name__)


@router.get("/register", response_class=HTMLResponse)
async def register_view(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="register.html"
    )


@router.post("/register", response_class=HTMLResponse)
def signup_user(
    request: Request,
    db: SessionDep,
    username: str = Form(),
    email: str = Form(),
    password: str = Form(),
    role: str = Form(),
    entry_path: str = Form(default=""),
    student_id: str = Form(default=""),
):
    service = AuthService(UserRepository(db))

    try:
        service.register_user(
            username,
            email,
            password,
            role=role,
            entry_path=entry_path or None,
            student_id=student_id or None,
        )

    except (ValueError, ValidationError) as exc:
        flash(request, str(exc), "danger")

        return RedirectResponse(
            url=request.url_for("register_view"),
            status_code=status.HTTP_303_SEE_OTHER
        )

    except IntegrityError:
        flash(
            request,
            "Username or email already exists",
            "danger"
        )

        return RedirectResponse(
            url=request.url_for("register_view"),
            status_code=status.HTTP_303_SEE_OTHER
        )

    except Exception:
        logger.exception("Registration failed unexpectedly")

        flash(
            request,
            "Registration could not be completed. Please try again.",
            "danger"
        )

        return RedirectResponse(
            url=request.url_for("register_view"),
            status_code=status.HTTP_303_SEE_OTHER
        )

    if role == "student":
        flash(
            request,
            "Student account created. Enrollment verification "
            "is required before browsing listings."
        )
    else:
        flash(
            request,
            "Landlord account created. Sign in now!"
        )

    return RedirectResponse(
        url=request.url_for("login_view"),
        status_code=status.HTTP_303_SEE_OTHER
    )
