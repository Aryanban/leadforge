from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from app.database import get_db
from app.models.send import Send
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

@router.get("/unsubscribe/{contact_id}")
async def unsubscribe(contact_id: int, db: AsyncSession = Depends(get_db)):
    from app.models.contact import Contact
    stmt = update(Contact).where(Contact.id == contact_id).values(unsubscribed=True)
    await db.execute(stmt)
    await db.commit()
    
    return {"message": "You have been successfully unsubscribed."}
