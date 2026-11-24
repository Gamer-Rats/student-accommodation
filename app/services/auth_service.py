
"""Browser authentication and signup services."""

from typing import Optional

from app.models.user import UserBase
from app.repositories.user import UserRepository
from app.utilities.security import (
    encrypt_password,
    verify_password,
    create_access_token,
)


class AuthService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def authenticate_user(
        self,
        username: str,
        password: str
    ) -> Optional[str]:
        user = self.user_repo.get_by_username(username)

        if not user or not verify_password(
            plaintext_password=password,
            encrypted_password=user.password
        ):
            return None

        return create_access_token(
            data={"sub": f"{user.id}", "role": user.role}
        )

    def register_user(
        self,
        username: str,
        email: str,
        password: str,
        *,
        role: str = "regular_user",
        entry_path: str | None = None,
        student_id: str | None = None,
    ):
        """Register a landlord or an unverified student."""

        username = username.strip()
        email = email.strip()

        if not username:
            raise ValueError("Username is required")

        if not email:
            raise ValueError("Email is required")

        if len(password) < 6:
            raise ValueError(
                "Password must contain at least six characters"
            )

        if role not in {"student", "landlord", "regular_user"}:
            raise ValueError(
                "Choose a valid student or landlord account type"
            )

        claimed_student_id: str | None = None

        if role == "student":
            if entry_path not in {"registered", "incoming"}:
                raise ValueError(
                    "Choose registered student or incoming student"
                )

            if entry_path == "registered":
                claimed_student_id = (student_id or "").strip()

                if not claimed_student_id:
                    raise ValueError(
                        "Registered students must provide their student ID"
                    )

                if len(claimed_student_id) > 32:
                    raise ValueError("Student ID is too long")

            elif student_id and student_id.strip():
                raise ValueError(
                    "Incoming students should not enter "
                    "a registered student ID"
                )

        elif entry_path or student_id:
            raise ValueError(
                "Enrollment details are only for student accounts"
            )

        new_user = UserBase(
            username=username,
            email=email,
            password=encrypt_password(password),
            role=role,
            student_id=None,
            provisional=0,
        )

        if role == "student":
            return self.user_repo.create_with_student_application(
                new_user,
                entry_path=entry_path,
                claimed_student_id=claimed_student_id,
            )

        return self.user_repo.create(new_user)
