
from __future__ import annotations

from typing import Any

from sqlmodel import Session

from app.repositories.listing import ListingRepository
from app.services import listings
from app.services.location_rules import (
    ALLOWED_AREAS,
    LOCATION_ERROR,
    normalize_area,
)


def _require_admin(actor_id: int) -> dict[str, Any] | None:
    """Return an error if the actor is not an administrator."""

    actor = listings.get_user(actor_id)

    if not actor or actor.get("role") != "admin":
        return {
            "ok": False,
            "error": "admin only",
        }

    return None


def release_admin_hold(
    actor_id: int,
    listing_id: int,
) -> dict[str, Any]:
    """Release a hold while requiring a fresh admin review."""

    error = _require_admin(actor_id)

    if error:
        return error

    with Session(listings.engine) as session:
        repository = ListingRepository(session)

        listing = repository.get_by_id(listing_id)

        if listing is None:
            return {
                "ok": False,
                "error": "listing not found",
            }

        if listing.status != "inactive":
            return {
                "ok": False,
                "error": (
                    "Only inactive listings can have "
                    "administrative holds released"
                ),
            }

        if not listing.admin_hold:
            return {
                "ok": False,
                "error": (
                    "listing is not on administrative hold"
                ),
            }

        # Removing the hold does not grant activation.
        # Administrator reverification is still required.
        listing.admin_hold = False
        listing.requires_reverification = True

        saved = repository.save(listing)

        return {
            "ok": True,
            "listing": saved.model_dump(),
        }


def complete_reverification(
    actor_id: int,
    listing_id: int,
) -> dict[str, Any]:
    """Clear reverification only after administrator approval."""

    error = _require_admin(actor_id)

    if error:
        return error

    with Session(listings.engine) as session:
        repository = ListingRepository(session)

        listing = repository.get_by_id(listing_id)

        if listing is None:
            return {
                "ok": False,
                "error": "listing not found",
            }

        if listing.status != "inactive":
            return {
                "ok": False,
                "error": (
                    "Only inactive listings can complete "
                    "this reverification workflow"
                ),
            }

        if listing.admin_hold:
            return {
                "ok": False,
                "error": (
                    "Release the administrative hold "
                    "before completing reverification"
                ),
            }

        if not listing.requires_reverification:
            return {
                "ok": False,
                "error": (
                    "listing does not require reverification"
                ),
            }

        # Recheck the existing location restriction.
        if normalize_area(listing.area) not in ALLOWED_AREAS:
            return {
                "ok": False,
                "error": LOCATION_ERROR,
            }

        # Check that essential listing details remain valid.
        if listing.price <= 0:
            return {
                "ok": False,
                "error": "price must be positive",
            }

        required_details = {
            "title": listing.title,
            "contact_phone": listing.contact_phone,
            "contact_email": listing.contact_email,
        }

        for field, value in required_details.items():
            if not isinstance(value, str) or not value.strip():
                return {
                    "ok": False,
                    "error": f"{field} is required",
                }

        # Administrator review is complete.
        # The owner must still activate the listing.
        listing.requires_reverification = False

        saved = repository.save(listing)

        return {
            "ok": True,
            "listing": saved.model_dump(),
        }
