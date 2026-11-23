"""Database model for accommodation listings."""

from typing import Optional

from sqlmodel import Field, SQLModel


class Listing(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    landlord_id: int = Field(index=True)

    title: str
    area: str
    price: int
    amenities: str = ""
    contact_phone: str
    contact_email: str
    photos: str = ""
    created_at: str

    # Single authoritative lifecycle status.
    status: str = Field(default="pending", index=True)

    # Additional metadata that does not duplicate status.
    review_feedback: str = Field(default="")
    admin_hold: bool = Field(default=False)
    requires_reverification: bool = Field(default=False)