
"""Listing CRUD, browsing, messaging, and lifecycle transitions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.database import engine
from app.models.listing import Listing
from app.models.message import Message
from app.services.housing_auth import get_user
from app.services.lifecycle import (
    ACTIONS,
    apply_action,
    visible_to_students,
)
from app.services.student_eligibility import student_access_error
from app.services.location_rules import (
    ALLOWED_AREAS,
    LOCATION_ERROR,
    normalize_area,
)


ADMIN_ACTIONS = {
    "verify",
    "provisionally_accept",
    "reject",
    "force_deactivate",
}

LANDLORD_ACTIONS = {
    "activate",
    "deactivate",
    "resubmit",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()


def _parse_amenities(raw: str) -> list[str]:
    """Return normalized, individual amenity names."""
    return [
        item.strip().casefold()
        for item in (raw or "").split(",")
        if item.strip()
    ]


def _available_to_students(
    listing: dict[str, Any],
) -> bool:
    """Check availability using lifecycle and location rules."""
    return (
        visible_to_students(listing)
        and normalize_area(listing.get("area")) in ALLOWED_AREAS
    )


def submit_listing(
    landlord_id: int,
    *,
    title: str,
    area: str,
    price: int,
    amenities: str,
    contact_phone: str,
    contact_email: str,
    photos: str = "",
) -> dict[str, Any]:
    user = get_user(landlord_id)

    if not user or user["role"] != "landlord":
        return {
            "ok": False,
            "error": "landlords only",
        }

    normalized_area = normalize_area(area)

    if normalized_area not in ALLOWED_AREAS:
        return {
            "ok": False,
            "error": LOCATION_ERROR,
        }

    if price <= 0:
        return {
            "ok": False,
            "error": "price must be positive",
        }

    with Session(engine) as session:
        listing = Listing(
            landlord_id=landlord_id,
            title=title,
            area=normalized_area,
            price=price,
            amenities=amenities,
            contact_phone=contact_phone,
            contact_email=contact_email,
            photos=photos,
            status="pending",
            created_at=_now(),
        )

        session.add(listing)
        session.commit()
        session.refresh(listing)

        return {
            "ok": True,
            "listing": listing.model_dump(),
        }


def transition(
    actor_id: int,
    listing_id: int,
    action: str,
) -> dict[str, Any]:
    actor = get_user(actor_id)

    if not actor:
        return {
            "ok": False,
            "error": "unknown user",
        }

    if action not in ACTIONS:
        return {
            "ok": False,
            "error": f"action must be one of {ACTIONS}",
        }

    with Session(engine) as session:
        listing = session.get(Listing, listing_id)

        if listing is None:
            return {
                "ok": False,
                "error": "listing not found",
            }

        if action in ADMIN_ACTIONS:
            if actor["role"] != "admin":
                return {
                    "ok": False,
                    "error": "admin only",
                }

        elif action in LANDLORD_ACTIONS:
            if actor["role"] != "landlord":
                return {
                    "ok": False,
                    "error": "landlord only",
                }

            if listing.landlord_id != actor_id:
                return {
                    "ok": False,
                    "error": "not listing owner",
                }

        if action in {
            "verify",
            "provisionally_accept",
            "activate",
        }:
            if normalize_area(listing.area) not in ALLOWED_AREAS:
                return {
                    "ok": False,
                    "error": LOCATION_ERROR,
                }

        row = listing.model_dump()
        result = apply_action(row, action)

        if not result.get("ok"):
            return result

        updated = result["row"]

        listing.status = updated["status"]
        listing.admin_hold = updated.get(
            "admin_hold", False
        )

        session.add(listing)
        session.commit()
        session.refresh(listing)

        return {
            "ok": True,
            "listing": listing.model_dump(),
        }


def browse_for_students(
    student_id: int,
    *,
    area: str | None = None,
    max_price: int | None = None,
    amenity: str | None = None,
) -> dict[str, Any]:
    student = get_user(student_id)

    error = student_access_error(student)

    if error:
        return {
            "ok": False,
            "error": error,
        }

    normalized_filter = None

    if area is not None:
        normalized_filter = normalize_area(area)

        if normalized_filter not in ALLOWED_AREAS:
            return {
                "ok": False,
                "error": LOCATION_ERROR,
            }

    requested_amenity = (
        amenity.strip().casefold()
        if amenity is not None
        else ""
    )

    with Session(engine) as session:
        rows = session.exec(
            select(Listing).order_by(Listing.id)
        ).all()

        items = [
            row.model_dump()
            for row in rows
        ]

    results = []

    for item in items:
        if not _available_to_students(item):
            continue

        item_area = normalize_area(item["area"])

        if (
            normalized_filter is not None
            and item_area != normalized_filter
        ):
            continue

        if (
            max_price is not None
            and int(item["price"]) > max_price
        ):
            continue

        if requested_amenity:
            listing_amenities = _parse_amenities(
                item["amenities"]
            )

            if requested_amenity not in listing_amenities:
                continue

        results.append(item)

    return {
        "ok": True,
        "listings": results,
    }


def list_all(
    *,
    status: str | None = None,
) -> list[dict[str, Any]]:
    with Session(engine) as session:
        stmt = select(Listing).order_by(Listing.id)

        if status:
            stmt = stmt.where(
                Listing.status == status
            )

        return [
            row.model_dump()
            for row in session.exec(stmt).all()
        ]


def list_for_landlord(landlord_id: int) -> dict[str, Any]:
    """Return only this landlord's listings, including non-public statuses."""
    actor = get_user(landlord_id)

    if not actor or actor["role"] != "landlord":
        return {
            "ok": False,
            "error": "landlords only",
        }

    with Session(engine) as session:
        rows = session.exec(
            select(Listing)
            .where(Listing.landlord_id == landlord_id)
            .order_by(Listing.id)
        ).all()

        return {
            "ok": True,
            "listings": [
                row.model_dump()
                for row in rows
            ],
        }


def send_message(
    student_id: int,
    listing_id: int,
    body: str,
) -> dict[str, Any]:
    student = get_user(student_id)

    error = student_access_error(student)

    if error:
        return {
            "ok": False,
            "error": error,
        }

    if not body.strip():
        return {
            "ok": False,
            "error": "body required",
        }

    with Session(engine) as session:
        listing = session.get(Listing, listing_id)

        if listing is None:
            return {
                "ok": False,
                "error": "listing not found",
            }

        if not _available_to_students(
            listing.model_dump()
        ):
            return {
                "ok": False,
                "error": "listing not available",
            }

        message = Message(
            listing_id=listing_id,
            student_id=student_id,
            body=body,
            created_at=_now(),
        )

        session.add(message)
        session.commit()
        session.refresh(message)

        return {
            "ok": True,
            "message_id": message.id,
        }


# Task #31: Ownership-protected listing editing.
# Only Pending and Rejected listings may be edited.
# Reviewed or publicly visible listings must not be changed
# without a separate administrator re-verification workflow.

EDITABLE_STATUSES = {"pending", "rejected"}

EDITABLE_FIELDS = {
    "title",
    "area",
    "price",
    "amenities",
    "contact_phone",
    "contact_email",
    "photos",
}

def update_listing(actor_id: int, listing_id: int, **changes: Any) -> dict[str, Any]:
    """Edit a landlord's listing without bypassing lifecycle rules."""

    actor = get_user(actor_id)
    if not actor or actor["role"] != "landlord":
        return {"ok": False, "error": "landlords only"}

    if not changes:
        return {"ok": False, "error": "no fields supplied"}

    forbidden = set(changes) - EDITABLE_FIELDS

    if forbidden:
        return {
            "ok": False,
            "error": "fields cannot be edited: "
            + ", ".join(sorted(forbidden)),
        }

    with Session(engine) as session:
        listing = session.get(Listing, listing_id)

        if listing is None:
            return {
                "ok": False,
                "error": "listing not found",
            }

        if listing.landlord_id != actor_id:
            return {
                "ok": False,
                "error": "not listing owner",
            }

        if listing.status not in EDITABLE_STATUSES:
            return {
                "ok": False,
                "error": (
                    "Only pending or rejected listings may be edited; "
                    "other listings require a separate review process"
                ),
            }

        # Validate all fields before modifying the database row.
        cleaned: dict[str, Any] = {}

        for field, value in changes.items():

            if field == "price":
                if type(value) is not int or value <= 0:
                    return {
                        "ok": False,
                        "error": "price must be a positive integer",
                    }

                cleaned[field] = value

            elif field == "area":
                if not isinstance(value, str):
                    return {
                        "ok": False,
                        "error": LOCATION_ERROR,
                    }

                area = normalize_area(value)

                if area not in ALLOWED_AREAS:
                    return {
                        "ok": False,
                        "error": LOCATION_ERROR,
                    }

                cleaned[field] = area

            else:
                if not isinstance(value, str):
                    return {
                        "ok": False,
                        "error": f"{field} must be text",
                    }

                value = value.strip()

                if field in {
                    "title",
                    "contact_phone",
                    "contact_email",
                } and not value:
                    return {
                        "ok": False,
                        "error": f"{field} is required",
                    }

                if field == "contact_email":
                    from pydantic import (
                        EmailStr,
                        TypeAdapter,
                        ValidationError,
                    )

                    try:
                        value = str(
                            TypeAdapter(EmailStr).validate_python(value)
                        )
                    except ValidationError:
                        return {
                            "ok": False,
                            "error": "invalid contact email",
                        }

                if field == "title" and len(value) > 200:
                    return {
                        "ok": False,
                        "error": "title is too long",
                    }

                cleaned[field] = value

        # All checks passed. Now update the listing.
        for field, value in cleaned.items():
            setattr(listing, field, value)

        session.add(listing)
        session.commit()
        session.refresh(listing)

        return {
            "ok": True,
            "listing": listing.model_dump(),
        }
