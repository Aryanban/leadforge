from fastapi import APIRouter, Depends, Request, Response, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from app.database import get_db
from app.models.send import Send
from app.campaigns.suppression import add_suppression
import base64

router = APIRouter()

# 1x1 transparent GIF
TRANSPARENT_PIXEL = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

@router.get("/open/{send_id}")
async def track_open(send_id: int, db: AsyncSession = Depends(get_db)):
    # Update send status asynchronously
    stmt = update(Send).where(Send.id == send_id).values(opened=True)
    await db.execute(stmt)
    await db.commit()
    
    return Response(content=TRANSPARENT_PIXEL, media_type="image/gif")


async def _suppress_contact(contact_id: int, db: AsyncSession) -> None:
    """Marks a contact unsubscribed and records a permanent global suppression.

    Both writes matter. The per-contact flag stops *this* row; the suppression
    row stops the address being re-imported by a later scrape and mailed again.
    """
    from app.models.contact import Contact
    from sqlalchemy import select

    contact = (
        await db.execute(select(Contact).where(Contact.id == contact_id))
    ).scalar_one_or_none()

    await db.execute(update(Contact).where(Contact.id == contact_id).values(unsubscribed=True))

    if contact is not None and contact.email:
        await add_suppression(db, contact.email, "unsubscribed", detail=f"contact_id={contact_id}")

    await db.commit()


@router.get("/unsubscribe/{contact_id}")
async def unsubscribe(contact_id: int, db: AsyncSession = Depends(get_db)):
    """Browser-facing one-click unsubscribe (the GET from the footer link)."""
    await _suppress_contact(contact_id, db)
    return {"message": "You have been successfully unsubscribed."}


@router.post("/unsubscribe/{contact_id}", status_code=http_status.HTTP_200_OK)
async def unsubscribe_post(
    contact_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """RFC 8058 one-click unsubscribe.

    Gmail and Yahoo POST to this URL when the recipient uses the in-client
    "Unsubscribe" button. We advertise it via `List-Unsubscribe-Post:
    List-Unsubscribe=One-Click` in every send, so this handler is mandatory -
    a missing or non-2xx response costs sender reputation. The body is
    `List-Unsubscribe=One-Click` form data and is intentionally ignored.
    """
    await _suppress_contact(contact_id, db)
    return Response(status_code=http_status.HTTP_200_OK)
