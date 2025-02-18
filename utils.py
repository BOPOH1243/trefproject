from datetime import datetime, timedelta
from passlib.context import CryptContext
import jwt
from config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=settings.access_token_expire_minutes))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return encoded_jwt

def create_email_confirmation_token(user_email: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.email_confirmation_expire_minutes)
    data = {"sub": user_email, "exp": expire}
    return jwt.encode(data, settings.jwt_secret, algorithm=settings.jwt_algorithm)
