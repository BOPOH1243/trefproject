from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
import uuid
from models import ReferralCode, User
from schemas import ReferralCodeCreate, ReferralCodeOut, UserOut
from database import get_db
from auth import get_current_active_user

router = APIRouter()

@router.post("/referral", response_model=ReferralCodeOut)
def create_referral_code(ref_data: ReferralCodeCreate, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    existing_code = db.query(ReferralCode).filter(ReferralCode.owner_id == current_user.id).first()
    if existing_code:
        raise HTTPException(status_code=400, detail="У вас уже есть активный реферальный код")
    
    code_str = str(uuid.uuid4())
    referral = ReferralCode(
        code=code_str,
        expiration_date=ref_data.expiration_date,
        owner_id=current_user.id,
    )
    db.add(referral)
    db.commit()
    db.refresh(referral)
    return referral

@router.delete("/referral", status_code=204)
def delete_referral_code(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    referral = db.query(ReferralCode).filter(ReferralCode.owner_id == current_user.id).first()
    if not referral:
        raise HTTPException(status_code=404, detail="Реферальный код не найден")
    db.delete(referral)
    db.commit()
    return

@router.get("/referral/by-email", response_model=ReferralCodeOut)
def get_referral_by_email(email: str = Query(...), db: Session = Depends(get_db)):
    from pydantic import EmailStr
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    referral = db.query(ReferralCode).filter(ReferralCode.owner_id == user.id).first()
    if not referral:
        raise HTTPException(status_code=404, detail="Реферальный код не найден")
    return referral

@router.get("/referrals/{referrer_id}", response_model=List[UserOut])
def get_referrals(referrer_id: int, db: Session = Depends(get_db)):
    referrals = db.query(User).filter(User.referred_by == referrer_id).all()
    return referrals
