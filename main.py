# main.py
# %% Импорты
from datetime import datetime, timedelta
from typing import Optional
import secrets
import uuid

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from fastapi_users import FastAPIUsers, models
from fastapi_users.authentication import JWTAuthentication
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, String, ForeignKey, DateTime, Boolean, Integer, Text, select #вроде как select правильно импортировал, можно закоммитить
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# %% Конфигурация
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
SECRET_KEY = secrets.token_urlsafe(32)
JWT_LIFETIME_SECONDS = 3600

# %% Модели
Base = declarative_base()

class User(SQLAlchemyBaseUserTableUUID, Base):
    referred_by = Column(String, ForeignKey("user.id"), nullable=True)
    referrals = relationship("User", backref="referrer", remote_side="id")
    referral_codes = relationship("ReferralCode", back_populates="user")

class ReferralCode(Base):
    __tablename__ = "referral_codes"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(36), unique=True, index=True)
    user_id = Column(String, ForeignKey("user.id"))
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    
    user = relationship("User", back_populates="referral_codes")

# %% Настройка базы данных
engine = create_async_engine(DATABASE_URL)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# %% Схемы
class UserCreate(models.BaseUserCreate):
    referral_code: Optional[str] = None

class UserRead(models.BaseUser[uuid.UUID]):
    referred_by: Optional[uuid.UUID] = None

class UserUpdate(models.BaseUserUpdate):
    pass

class ReferralCodeCreate(BaseModel):
    days_valid: int

class ReferralCodeResponse(BaseModel):
    code: str
    expires_at: datetime
    is_active: bool

# %% Настройка аутентификации
jwt_authentication = JWTAuthentication(
    secret=SECRET_KEY,
    lifetime_seconds=JWT_LIFETIME_SECONDS,
    tokenUrl="auth/jwt/login"
)

# %% FastAPI Users setup
async def get_user_db(session: AsyncSession = Depends(async_session_maker)):
    yield SQLAlchemyUserDatabase(session, User)

fastapi_users = FastAPIUsers(
    get_user_db,
    [jwt_authentication],
    User,
    UserCreate,
    UserUpdate,
    UserRead,
)

# %% Роутеры
app = FastAPI(title="Referral System API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    await create_db_and_tables()

# Аутентификация
app.include_router(
    fastapi_users.get_auth_router(jwt_authentication),
    prefix="/auth/jwt",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)

# Реферальные эндпоинты
@app.post("/referral-codes/", response_model=ReferralCodeResponse, tags=["referral"])
async def create_referral_code(
    data: ReferralCodeCreate,
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(async_session_maker)
):
    # Проверка существующего активного кода
    existing_code = await session.execute(
        select(ReferralCode).where(
            (ReferralCode.user_id == str(user.id)) &
            (ReferralCode.is_active == True)
        )
    )
    if existing_code.scalar():
        raise HTTPException(
            status_code=400,
            detail="Active referral code already exists"
        )

    # Генерация нового кода
    code = secrets.token_urlsafe(16)
    expires_at = datetime.utcnow() + timedelta(days=data.days_valid)
    
    new_code = ReferralCode(
        code=code,
        user_id=str(user.id),
        expires_at=expires_at
    )
    
    session.add(new_code)
    await session.commit()
    return new_code

@app.delete("/referral-codes/{code_id}", tags=["referral"])
async def delete_referral_code(
    code_id: str,
    user: User = Depends(fastapi_users.current_user(active=True)),
    session: AsyncSession = Depends(async_session_maker)
):
    code = await session.get(ReferralCode, code_id)
    if not code or code.user_id != str(user.id):
        raise HTTPException(status_code=404, detail="Code not found")
    
    code.is_active = False
    await session.commit()
    return {"status": "success"}

@app.get("/referral-code/{email}", response_model=ReferralCodeResponse, tags=["referral"])
async def get_referral_code_by_email(
    email: EmailStr,
    session: AsyncSession = Depends(async_session_maker)
):
    user = await session.execute(select(User).where(User.email == email))
    user = user.scalar()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    code = await session.execute(
        select(ReferralCode).where(
            (ReferralCode.user_id == str(user.id)) &
            (ReferralCode.is_active == True)
        )
    )
    code = code.scalar()
    if not code:
        raise HTTPException(status_code=404, detail="Active code not found")
    
    return code

@app.get("/users/{user_id}/referrals", tags=["referral"])
async def get_referrals(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(async_session_maker)
):
    referrals = await session.execute(
        select(User).where(User.referred_by == str(user_id))
    )
    return referrals.scalars().all()

# Регистрация с реферальным кодом
@app.post("/register-with-referral", tags=["auth"])
async def register_with_referral(
    user_create: UserCreate,
    session: AsyncSession = Depends(async_session_maker)
):
    if user_create.referral_code:
        referral_code = await session.execute(
            select(ReferralCode).where(
                (ReferralCode.code == user_create.referral_code) &
                (ReferralCode.is_active == True) &
                (ReferralCode.expires_at >= datetime.utcnow())
            )
        )
        referral_code = referral_code.scalar()
        if not referral_code:
            raise HTTPException(status_code=400, detail="Invalid referral code")
        
        user_create.referred_by = referral_code.user_id
    
    user_db = SQLAlchemyUserDatabase(session, User)
    return await user_db.create(await user_db.validate(user_create))

# %% Запуск
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)