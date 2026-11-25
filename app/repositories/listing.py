
from sqlmodel import Session, select

from app.models.listing import Listing
from app.models.message import Message
from app.models.user import User


class ListingRepository:
    """Handle listing and message persistence."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(
        self,
        listing_id: int,
    ) -> Listing | None:
        """Retrieve one accommodation listing."""

        return self.db.get(
            Listing,
            listing_id,
        )

    def get_all(
        self,
        *,
        status: str | None = None,
    ) -> list[Listing]:
        """Retrieve all listings, optionally filtered by status."""

        statement = select(Listing).order_by(
            Listing.id
        )

        if status:
            statement = statement.where(
                Listing.status == status
            )

        return list(
            self.db.exec(statement).all()
        )

    def get_by_landlord(
        self,
        landlord_id: int,
    ) -> list[Listing]:
        """Retrieve listings owned by a particular landlord."""

        statement = (
            select(Listing)
            .where(
                Listing.landlord_id == landlord_id
            )
            .order_by(Listing.id)
        )

        return list(
            self.db.exec(statement).all()
        )

    def get_inbox_by_landlord(
        self,
        landlord_id: int,
    ) -> list[tuple[Message, Listing, User | None]]:
        """Retrieve a landlord's messages with listing and student details."""

        statement = (
            select(Message, Listing, User)
            .join(
                Listing,
                Message.listing_id == Listing.id,
            )
            .outerjoin(
                User,
                Message.student_id == User.id,
            )
            .where(
                Listing.landlord_id == landlord_id,
            )
            .order_by(
                Message.created_at.desc(),
                Message.id.desc(),
            )
        )

        return list(
            self.db.exec(statement).all()
        )

    def create(
        self,
        listing: Listing,
    ) -> Listing:
        """Save a newly submitted listing."""

        try:
            self.db.add(listing)
            self.db.commit()
            self.db.refresh(listing)

            return listing

        except Exception:
            self.db.rollback()
            raise

    def save(
        self,
        listing: Listing,
    ) -> Listing:
        """Persist changes to an existing listing."""

        try:
            self.db.add(listing)
            self.db.commit()
            self.db.refresh(listing)

            return listing

        except Exception:
            self.db.rollback()
            raise

    def create_message(
        self,
        message: Message,
    ) -> Message:
        """Store a student's message about a listing."""

        try:
            self.db.add(message)
            self.db.commit()
            self.db.refresh(message)

            return message

        except Exception:
            self.db.rollback()
            raise
