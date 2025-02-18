from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_confirmed = Column(Boolean, default=False)
    referred_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    referral_code = relationship("ReferralCode", back_populates="owner", uselist=False)
    referrals = relationship("User", backref="referrer", remote_side=[id])

class ReferralCode(Base):
    __tablename__ = "referral_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    expiration_date = Column(DateTime, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("User", back_populates="referral_code")
