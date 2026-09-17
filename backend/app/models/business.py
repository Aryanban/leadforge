from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Business(Base):
    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True, index=True)
    place_id = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, index=True)
    website = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    rating = Column(Float, nullable=True)
    reviews_count = Column(Integer, nullable=True)
    industry = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    maps_url = Column(String, nullable=True)
    extra_data = Column(JSON, nullable=True)

    source = Column(String, nullable=True)
    icp_profile_id = Column(Integer, ForeignKey("icp_profiles.id"), nullable=True, index=True)
    icp_fit = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    contacts = relationship("Contact", back_populates="business", cascade="all, delete-orphan")
    icp_profile = relationship("ICPProfile", back_populates="businesses")
