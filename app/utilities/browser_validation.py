
"""Task #52: Shared browser form validation.

Provides consistent validation rules and safe,
user-friendly error messages for accommodation forms.
"""

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.services.location_rules import (
    ALLOWED_AREAS,
    normalize_area,
)


EMAIL_VALIDATOR = TypeAdapter(EmailStr)


def validate_listing_form(
    *,
    title: str,
    area: str,
    price: str,
    amenities: str = "",
    contact_phone: str,
    contact_email: str,
    photos: str = "",
) -> dict:
    """Validate and clean accommodation form inputs.

    Returns:
        {
            "ok": True,
            "data": {validated fields}
        }

    or:
        {
            "ok": False,
            "error": "User-friendly explanation"
        }

    No database changes are performed here.
    """

    cleaned_title = title.strip()
    cleaned_phone = contact_phone.strip()
    cleaned_email = contact_email.strip()

    # Validate title.
    if not cleaned_title:
        return {
            "ok": False,
            "error": "Listing title is required.",
        }

    if len(cleaned_title) > 200:
        return {
            "ok": False,
            "error": (
                "Listing title must not exceed "
                "200 characters."
            ),
        }

    # Validate accommodation location.
    normalized_area = normalize_area(area)

    if normalized_area not in ALLOWED_AREAS:
        return {
            "ok": False,
            "error": (
                "Accommodation location must be "
                "St. Augustine or Mount Hope."
            ),
        }

    # Validate monthly rent.
    try:
        numeric_price = int(price.strip())

    except (ValueError, TypeError):
        return {
            "ok": False,
            "error": (
                "Monthly rent must be a whole number."
            ),
        }

    if numeric_price <= 0:
        return {
            "ok": False,
            "error": (
                "Monthly rent must be greater than zero."
            ),
        }

    # Validate contact details.
    if not cleaned_phone:
        return {
            "ok": False,
            "error": "Contact phone number is required.",
        }

    if not cleaned_email:
        return {
            "ok": False,
            "error": "Contact email address is required.",
        }

    # Validate email address format.
    try:
        validated_email = str(
            EMAIL_VALIDATOR.validate_python(
                cleaned_email
            )
        )

    except ValidationError:
        return {
            "ok": False,
            "error": (
                "Enter a valid contact email address."
            ),
        }

    # Return clean values only after all checks pass.
    return {
        "ok": True,
        "data": {
            "title": cleaned_title,
            "area": normalized_area,
            "price": numeric_price,
            "amenities": amenities.strip(),
            "contact_phone": cleaned_phone,
            "contact_email": validated_email,
            "photos": photos.strip(),
        },
    }
