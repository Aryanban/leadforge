from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base

class Mailbox(Base):
    __tablename__ = "mailboxes"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)  # In prod, this can be encrypted
    smtp_host = Column(String)
    smtp_port = Column(Integer, default=587)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    
    daily_limit = Column(Integer, default=50)
    sent_today = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
