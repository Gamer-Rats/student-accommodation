
"""Student-accommodation JSON API with authenticated user identity."""

from __future__ import annotations

from typing import Annotated, Any

import jwt
from jwt.exceptions import InvalidTokenError

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services import housing_auth as auth
from app.services import listings
from app.services.location_rules import LOCATION_ERROR
from app.utilities.security import create_access_token


router = APIRouter(tags=["student-accommodation"])

bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="StudentAccommodationBearer",
    description="Sign in at POST /api/auth/login and paste the access_token.",
)


class LoginBody(BaseModel):
    email: str
    password: str


class ListingBody(BaseModel):
    title: str
    area: str
    price: int
    amenities: str = ""
    contact_phone: str
    contact_email: str
    photos: str = ""



class TransitionBody(BaseModel):
    action: str = Field(
        description=(
            "verify | provisionally_accept | reject | "
            "activate | deactivate | force_deactivate | resubmit"
        )
    )

    review_feedback: str | None = Field(
        default=None,
        description=(
            "Administrator rejection reason. "
            "Required when action is reject."
        ),
    )



class MessageBody(BaseModel):
    listing_id: int
    body: str


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def authenticated_actor(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> dict[str, Any]:
    """Identify the caller using a verified signed token.

    Bearer tokens work for all API methods.

    Existing browser authentication cookies are supported for
    GET requests. API write operations require a Bearer token.

    The old X-User-Id header is deliberately ignored.
    """

    authorization_header = request.headers.get("authorization")

    if authorization_header is not None:
        if (
            credentials is None
            or credentials.scheme.lower() != "bearer"
        ):
            raise _unauthorized()

        token = credentials.credentials

    elif request.method.upper() == "GET":
        token = request.cookies.get("access_token")

    else:
        token = None

    if not token:
        raise _unauthorized()

    try:
        settings = get_settings()

        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )

        subject = payload.get("sub")

        if not isinstance(subject, str) or not subject.isdecimal():
            raise ValueError("Token subject must be a numeric user ID")

        user_id = int(subject)

        if user_id <= 0:
            raise ValueError("Invalid user ID")

    except (InvalidTokenError, TypeError, ValueError) as exc:
        raise _unauthorized() from exc

    # Get the actual account from the database.
    # Never trust a role supplied by the caller or stored in the token.
    actor = auth.get_user(user_id)

    if actor is None:
        raise _unauthorized()

    return actor


Actor = Annotated[
    dict[str, Any],
    Depends(authenticated_actor),
]


@router.post("/auth/login")
def login(body: LoginBody) -> dict[str, Any]:
    user = auth.login(body.email, body.password)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="invalid credentials",
        )

    token = create_access_token(
        data={"sub": str(user["id"])}
    )

    return {
        "user": user,
        "access_token": token,
        "token_type": "bearer",
    }


@router.post("/landlord/listings")
def submit(
    body: ListingBody,
    actor: Actor,
) -> dict[str, Any]:

    result = listings.submit_listing(
        actor["id"],
        title=body.title,
        area=body.area,
        price=body.price,
        amenities=body.amenities,
        contact_phone=body.contact_phone,
        contact_email=body.contact_email,
        photos=body.photos,
    )

    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error"),
        )

    return result



@router.post("/listings/{listing_id}/transition")
def transition(
    listing_id: int,
    body: TransitionBody,
    actor: Actor,
) -> dict[str, Any]:

    result = listings.transition(
        actor["id"],
        listing_id,
        body.action,
        review_feedback=body.review_feedback,
    )

    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error"),
        )

    return result



@router.get("/student/listings")
def browse(
    actor: Actor,
    area: str | None = None,
    max_price: int | None = None,
    amenity: str | None = None,
) -> dict[str, Any]:

    result = listings.browse_for_students(
        actor["id"],
        area=area,
        max_price=max_price,
        amenity=amenity,
    )

    if not result.get("ok"):
        code = (
            400
            if result.get("error") == LOCATION_ERROR
            else 403
        )

        raise HTTPException(
            status_code=code,
            detail=result.get("error"),
        )

    return result


@router.get("/admin/listings")
def admin_list(
    actor: Actor,
    status: str | None = None,
) -> dict[str, Any]:

    if actor["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail="admin only",
        )

    return {
        "listings": listings.list_all(status=status)
    }


@router.post("/student/messages")
def message(
    body: MessageBody,
    actor: Actor,
) -> dict[str, Any]:

    result = listings.send_message(
        actor["id"],
        body.listing_id,
        body.body,
    )

    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error"),
        )

    return result
