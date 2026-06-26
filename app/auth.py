from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeSerializer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

COOKIE_NAME = "session"
_serializer = URLSafeSerializer(settings.secret_key, salt="session")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def make_session_cookie(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def read_session_cookie(value: str) -> int | None:
    try:
        data = _serializer.loads(value)
        return int(data["uid"])
    except (BadSignature, KeyError, ValueError, TypeError):
        return None


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == username).first()
    if user and verify_password(password, user.password_hash):
        return user
    return None


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    uid = read_session_cookie(cookie)
    if uid is None:
        return None
    return db.get(User, uid)


def require_user(
    request: Request, user: User | None = Depends(current_user)
) -> User:
    """Любой авторизованный пользователь (admin или viewer)."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    return user


def require_admin(
    request: Request, user: User | None = Depends(current_user)
) -> User:
    """Только администратор. Viewer получает 403."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права администратора",
        )
    return user
