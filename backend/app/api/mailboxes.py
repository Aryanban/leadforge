from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel, EmailStr
from typing import Optional, List

from app.database import get_db
from app.models.mailbox import Mailbox
from app.campaigns.sender import test_smtp_connection

router = APIRouter()

class MailboxCreate(BaseModel):
    email: str
    password: str
    smtp_host: str
    smtp_port: int = 587
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    daily_limit: int = 50

@router.get("")
@router.get("/")
async def list_mailboxes(db: AsyncSession = Depends(get_db)):
    stmt = select(Mailbox).order_by(Mailbox.id.desc())
    res = await db.execute(stmt)
    mailboxes = res.scalars().all()
    return [
        {
            "id": m.id,
            "email": m.email,
            "smtp_host": m.smtp_host,
            "smtp_port": m.smtp_port,
            "first_name": m.first_name,
            "last_name": m.last_name,
            "daily_limit": m.daily_limit,
            "sent_today": m.sent_today,
            "is_active": m.is_active,
            "created_at": m.created_at.isoformat() if m.created_at else None
        }
        for m in mailboxes
    ]


@router.post("/")
async def create_mailbox(req: MailboxCreate, db: AsyncSession = Depends(get_db)):
    # Check if already exists
    stmt = select(Mailbox).where(Mailbox.email == req.email.strip().lower())
    res = await db.execute(stmt)
    existing = res.scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Mailbox with this email already exists")

    mailbox = Mailbox(
        email=req.email.strip().lower(),
        password=req.password,
        smtp_host=req.smtp_host.strip(),
        smtp_port=req.smtp_port,
        first_name=req.first_name,
        last_name=req.last_name,
        daily_limit=req.daily_limit,
        sent_today=0,
        is_active=True
    )
    db.add(mailbox)
    await db.commit()
    await db.refresh(mailbox)

    return {
        "id": mailbox.id,
        "email": mailbox.email,
        "status": "created"
    }


@router.post("/{mailbox_id}/test")
async def test_mailbox(mailbox_id: int, db: AsyncSession = Depends(get_db)):
    mailbox = await db.get(Mailbox, mailbox_id)
    if not mailbox:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    success, msg = test_smtp_connection(
        host=mailbox.smtp_host,
        port=mailbox.smtp_port,
        user=mailbox.email,
        password=mailbox.password
    )

    return {
        "success": success,
        "message": msg if success else f"SMTP test failed: {msg}"
    }


@router.delete("/{mailbox_id}")
async def delete_mailbox(mailbox_id: int, db: AsyncSession = Depends(get_db)):
    stmt = delete(Mailbox).where(Mailbox.id == mailbox_id)
    await db.execute(stmt)
    await db.commit()
    return {"status": "deleted", "id": mailbox_id}
