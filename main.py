# main.py

# region Imports & Конфигурация
from datetime import datetime, timedelta
import uuid
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from passlib.context import CryptContext
import jwt
from fastapi_mail import ConnectionConfig
from fastapi import BackgroundTasks, HTTPException
from fastapi_mail import FastMail, MessageSchema

HOST_DOMAIN='127.0.0.1:8000'
MAIL_USERNAME='tenpenni@mail.ru'
MAIL_PASSWORD='1d1itC4VwEn1XzXF61sA'
MAIL_FROM='tenpenni@mail.ru'
MAIL_PORT=465
MAIL_SERVER='smtp.mail.ru'
MAIL_TLS=True
MAIL_SSL=False
TEMPLATE_FOLDER='./templates'
# region Mail
conf = ConnectionConfig(
    MAIL_USERNAME=MAIL_USERNAME,
    MAIL_PASSWORD=MAIL_PASSWORD,
    MAIL_FROM=MAIL_FROM,
    MAIL_PORT=MAIL_PORT,
    MAIL_SERVER=MAIL_SERVER,
    MAIL_SSL_TLS=True,
    MAIL_STARTTLS=False,
    TEMPLATE_FOLDER=TEMPLATE_FOLDER
)

async def send_verification_email(email_to: str, token: str):
    verification_url = f"http://{HOST_DOMAIN}/confirm-email?token={token}"
    message = MessageSchema(
        subject="Подтверждение email",
        recipients=[email_to],
        template_body={"verification_url": verification_url},
        subtype="html"
    )
    
    fm = FastMail(conf)
    await fm.send_message(message, template_name='verification_email.html')
# endregion

# --- Конфигурация БД ---
DB_USER = "your_user"
DB_PASSWORD = "your_password"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "your_database"
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# --- Конфигурация JWT ---
JWT_SECRET = "your_jwt_secret_key"
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
EMAIL_CONFIRMATION_EXPIRE_MINUTES = 60  # токен для подтверждения email

# OAuth2 схема
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

# Пароль хеширование
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# endregion

# region DB
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
# endregion

# region Models
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_confirmed = Column(Boolean, default=False)
    # Для реферальной регистрации: указываем, кто пригласил пользователя
    referred_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Реферальный код, созданный пользователем (один активный код)
    referral_code = relationship("ReferralCode", back_populates="owner", uselist=False)
    # Пользователи, которые зарегистрировались по реферальной ссылке этого пользователя
    referrals = relationship("User", backref="referrer", remote_side=[id])

class ReferralCode(Base):
    __tablename__ = "referral_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    expiration_date = Column(DateTime, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("User", back_populates="referral_code")
# endregion

# region Schemas (Pydantic модели)
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    referral_code: Optional[str] = None  # код, по которому пользователь зарегистрировался

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
# endregion

# region Utils: password hashing и токены
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def create_email_confirmation_token(user_email: str):
    expire = datetime.utcnow() + timedelta(minutes=EMAIL_CONFIRMATION_EXPIRE_MINUTES)
    data = {"sub": user_email, "exp": expire}
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGORITHM)
# endregion

# region Authentication Dependencies
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось проверить учетные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
        token_data = TokenData(user_id=user_id)
    except jwt.PyJWTError:
        raise credentials_exception
    user = db.query(User).filter(User.id == token_data.user_id).first()
    if user is None:
        raise credentials_exception
    return user

def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Неактивный пользователь")
    return current_user
# endregion

# region FastAPI app и endpoints
app = FastAPI(title="Referral System API")

# --- Создание БД ---
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

# Регистрация пользователя с подтверждением email
@app.post("/register", response_model=UserOut)
def register(user_in: UserCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # Проверка, существует ли уже пользователь с таким email
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")
    
    # Если указан реферальный код, проверяем его валидность
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

    # Создаем токен подтверждения email и имитируем отправку письма (например, через background task)
    email_token = create_email_confirmation_token(new_user.email)
    # confirmation_link = f"http://localhost:8000/confirm-email?token={email_token}"
    # Здесь можно добавить отправку письма, пока что просто выводим ссылку в консоль
    background_tasks.add_task(send_verification_email, new_user.email, email_token)

    return new_user

# Подтверждение email
@app.get("/confirm-email")
def confirm_email(token: str, db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
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

# Аутентификация: получение JWT токена
@app.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Неверный email или пароль")
    access_token = create_access_token(data={"user_id": user.id})
    return {"access_token": access_token, "token_type": "bearer"}

# Создание реферального кода (аутентифицированный пользователь)
@app.post("/referral", response_model=ReferralCodeOut)
def create_referral_code(ref_data: ReferralCodeCreate, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    # Проверка: если пользователь уже имеет активный код, выдаем ошибку
    existing_code = db.query(ReferralCode).filter(ReferralCode.owner_id == current_user.id).first()
    if existing_code:
        raise HTTPException(status_code=400, detail="У вас уже есть активный реферальный код")
    
    # Генерация уникального кода (например, UUID)
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

# Удаление реферального кода
@app.delete("/referral", status_code=204)
def delete_referral_code(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    referral = db.query(ReferralCode).filter(ReferralCode.owner_id == current_user.id).first()
    if not referral:
        raise HTTPException(status_code=404, detail="Реферальный код не найден")
    db.delete(referral)
    db.commit()
    return

# Получение реферального кода по email адресу реферера
@app.get("/referral/by-email", response_model=ReferralCodeOut)
def get_referral_by_email(email: EmailStr = Query(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    referral = db.query(ReferralCode).filter(ReferralCode.owner_id == user.id).first()
    if not referral:
        raise HTTPException(status_code=404, detail="Реферальный код не найден")
    return referral

# Получение информации о рефералах по id реферера
@app.get("/referrals/{referrer_id}", response_model=List[UserOut])
def get_referrals(referrer_id: int, db: Session = Depends(get_db)):
    referrals = db.query(User).filter(User.referred_by == referrer_id).all()
    return referrals
# endregion

# region Main запуск
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
# endregion
