from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    referral_code: Optional[str] = None

class UserOut(BaseModel):
    id: int
    email: EmailStr
    is_active: bool
    is_confirmed: bool
    referred_by: Optional[int] = None

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: Optional[int] = None

class ReferralCodeCreate(BaseModel):
    expiration_date: datetime = Field(..., description="Дата и время истечения кода (UTC)")

class ReferralCodeOut(BaseModel):
    code: str
    expiration_date: datetime

    class Config:
        from_attributes = True
