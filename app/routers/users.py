
"""User directory API restricted to campus administrators."""

from fastapi import HTTPException, status

from app.dependencies import SessionDep
from app.dependencies.auth import AuthDep
from app.repositories.user import UserRepository
from app.schemas import UserResponse
from app.services.user_service import UserService

from . import api_router


@api_router.get("/users", response_model=list[UserResponse])
async def list_users(
    db: SessionDep,
    current_user: AuthDep,
):
    """
    Return the user directory to authenticated
    campus administrators only.
    """

    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrators only",
        )

    user_repo = UserRepository(db)
    user_service = UserService(user_repo)

    return user_service.get_all_users()
