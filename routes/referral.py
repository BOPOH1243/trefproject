from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
import uuid
from models import ReferralCode, User
from schemas import ReferralCodeCreate, ReferralCodeOut, UserOut
from database import get_db
from auth import get_current_active_user

router = APIRouter(
    prefix="/referral",
    tags=["Referral"],
    responses={404: {"description": "Not found"}}
)

@router.post("", response_model=ReferralCodeOut, summary="Создание реферального кода",
             description="Создает уникальный реферальный код для аутентифицированного пользователя. Если код уже существует, возвращается ошибка.")
def create_referral_code(ref_data: ReferralCodeCreate, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """
    Создает новый реферальный код.

    - **expiration_date**: Дата и время истечения кода (UTC).
    """
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

@router.delete("", status_code=204, summary="Удаление реферального кода",
               description="Удаляет реферальный код аутентифицированного пользователя.")
def delete_referral_code(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """
    Удаляет реферальный код пользователя.
    """
    referral = db.query(ReferralCode).filter(ReferralCode.owner_id == current_user.id).first()
    if not referral:
        raise HTTPException(status_code=404, detail="Реферальный код не найден")
    db.delete(referral)
    db.commit()
    return

@router.get("/by-email", response_model=ReferralCodeOut, summary="Получение реферального кода по email",
            description="Возвращает реферальный код пользователя по заданному email адресу.")
def get_referral_by_email(email: str = Query(...), db: Session = Depends(get_db)):
    """
    Получает реферальный код по email.

    - **email**: Email пользователя, чей реферальный код требуется найти.
    """
    from pydantic import EmailStr
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    referral = db.query(ReferralCode).filter(ReferralCode.owner_id == user.id).first()
    if not referral:
        raise HTTPException(status_code=404, detail="Реферальный код не найден")
    return referral

@router.get("/referrals/{referrer_id}", response_model=List[UserOut], summary="Получение списка рефералов",
            description="Возвращает список пользователей, зарегистрированных по реферальной ссылке заданного пользователя.")
def get_referrals(referrer_id: int, db: Session = Depends(get_db)):
    """
    Получает список рефералов для указанного реферера.

    - **referrer_id**: ID пользователя, который является реферером.
    """
    referrals = db.query(User).filter(User.referred_by == referrer_id).all()
    return referrals
