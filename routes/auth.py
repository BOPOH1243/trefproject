from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from datetime import datetime
from sqlalchemy.orm import Session
import jwt
from fastapi.security import OAuth2PasswordRequestForm
from config import settings
from models import User, ReferralCode
from schemas import UserCreate, UserOut, Token
from database import get_db
from utils import get_password_hash, verify_password, create_access_token, create_email_confirmation_token
from mail import send_verification_email
from auth import oauth2_scheme, redis_client

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    responses={404: {"description": "Not found"}}
)

@router.post("/register", response_model=UserOut, summary="Регистрация пользователя",
             description="Регистрация нового пользователя. При наличии реферального кода происходит проверка его валидности. После регистрации отправляется email для подтверждения аккаунта.")
def register(user_in: UserCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Регистрирует нового пользователя и инициирует процесс подтверждения email.
    
    - **email**: Email пользователя.
    - **password**: Пароль пользователя.
    - **referral_code**: (необязательно) Реферальный код, по которому зарегистрировался пользователь.
    """
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")
    
    referred_by_id = None
    if user_in.referral_code:
        referral = db.query(ReferralCode).filter(ReferralCode.code == user_in.referral_code).first()
        if not referral:
            raise HTTPException(status_code=400, detail="Неверный реферальный код")
        if referral.expiration_date < datetime.utcnow():
            raise HTTPException(status_code=400, detail="Реферальный код истёк")
        referred_by_id = referral.owner_id

    hashed_password = get_password_hash(user_in.password)
    new_user = User(
        email=user_in.email,
        hashed_password=hashed_password,
        is_active=True,
        is_confirmed=False,
        referred_by=referred_by_id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    email_token = create_email_confirmation_token(new_user.email)
    background_tasks.add_task(send_verification_email, new_user.email, email_token)

    return new_user

@router.get("/confirm-email", summary="Подтверждение email",
            description="Подтверждение email пользователя с помощью токена, полученного в письме.")
def confirm_email(token: str, db: Session = Depends(get_db)):
    """
    Подтверждает email пользователя по переданному токену.

    - **token**: Токен подтверждения, полученный на email.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_email: str = payload.get("sub")
        if user_email is None:
            raise HTTPException(status_code=400, detail="Неверный токен")
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="Неверный или просроченный токен")
    
    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.is_confirmed = True
    db.commit()
    return {"message": "Email успешно подтвержден"}

@router.post("/token", response_model=Token, summary="Аутентификация пользователя",
             description="Возвращает JWT токен для аутентифицированного пользователя, если email и пароль корректны.")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Аутентифицирует пользователя и возвращает JWT токен.

    - **username**: Email пользователя.
    - **password**: Пароль пользователя.
    """
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Неверный email или пароль")
    access_token = create_access_token(data={"user_id": user.id})
    ttl_seconds = settings.access_token_expire_minutes * 60
    redis_key = f"jwt:{access_token}"
    redis_client.set(redis_key, user.id, ex=ttl_seconds)
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout", summary="Выход из системы",
             description="Отзыв JWT токена для выхода из системы.")
def logout(token: str = Depends(oauth2_scheme)):
    """
    Отзывает JWT токен, завершая сессию пользователя.
    """
    redis_key = f"jwt:{token}"
    redis_client.delete(redis_key)
    return {"message": "Вы успешно вышли из системы"}
