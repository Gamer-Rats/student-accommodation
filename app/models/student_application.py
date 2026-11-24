
"""Pending eligibility claims from newly registered student accounts."""

from typing import Optional

from sqlmodel import Field, SQLModel


class StudentApplication(SQLModel, table=True):
    """Student registration details awaiting verification."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", unique=True, index=True)
    entry_path: str
    claimed_student_id: Optional[str] = None
    status: str = "pending"
