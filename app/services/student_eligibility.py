
from typing import Any, Mapping


def is_eligible_student( user: Mapping[str, Any] | None,) -> bool:

    if not user or user.get("role") != "student":
        return False

    student_id = user.get("student_id")

    has_student_id = (
        isinstance(student_id, str)
        and bool(student_id.strip())
    )

    is_provisional = user.get("provisional", 0) == 1

    return has_student_id or is_provisional


def student_access_error(
    user: Mapping[str, Any] | None,
) -> str | None:

    if not user or user.get("role") != "student":
        return "students only"

    if not is_eligible_student(user):
        return "student eligibility required"

    return None
