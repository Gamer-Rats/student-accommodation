
"""Login pages with CSRF protection."""

from fastapi import Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.dependencies import SessionDep
from app.repositories.user import UserRepository
from app.services.auth_service import AuthService
from app.utilities.csrf import (
    get_csrf_token,
    validate_csrf_token,
    rotate_csrf_token,
)
from app.utilities.flash import flash
from app.utilities.security import access_token_cookie_kwargs

from . import router, templates


@router.get(
    "/login",
    response_class=HTMLResponse,
)
async def login_view(request: Request):
    """Display the login form with a CSRF token."""

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "csrf_token": get_csrf_token(request),
        },
    )


@router.post(
    "/login",
    response_class=HTMLResponse,
)
async def login_action_ajax(
    db: SessionDep,
    request: Request,
    username: str = Form(),
    password: str = Form(),
    csrf_token: str = Form(default=""),
):
    """Authenticate a user only after checking the CSRF token."""

    validate_csrf_token(
        request,
        csrf_token,
    )

    user_repo = UserRepository(db)

    auth_service = AuthService(user_repo)

    access_token = auth_service.authenticate_user(
        username,
        password,
    )

    if not access_token:
        flash(
            request,
            "Incorrect username or password",
            "danger",
        )

        return RedirectResponse(
            url=request.url_for("login_view"),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    user = user_repo.get_by_username(username)

    dest = (
        "admin_home_view"
        if user and user.role == "admin"
        else "user_home_view"
    )

    # Generate a fresh token after successful authentication.
    rotate_csrf_token(request)

    response = RedirectResponse(
        url=request.url_for(dest),
        status_code=status.HTTP_303_SEE_OTHER,
    )

    response.set_cookie(
        key="access_token",
        value=access_token,
        **access_token_cookie_kwargs(),
    )

    return response
