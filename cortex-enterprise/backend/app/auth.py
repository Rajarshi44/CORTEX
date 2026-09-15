"""JWT authentication, role-based authorisation and audit logging."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import AuditLog, User, get_session

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
ROLE_RANK = {"viewer": 0, "analyst": 1, "admin": 2}


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=10)).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user: User) -> str:
    payload = {"sub": user.username, "role": user.role, "name": user.full_name,
               "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def bootstrap_users(db: Session) -> None:
    if db.query(User).count() == 0:
        db.add(User(username=settings.bootstrap_admin_user, password_hash=hash_password(settings.bootstrap_admin_password),
                    role="admin", full_name="System Administrator"))
        db.add(User(username=settings.bootstrap_analyst_user, password_hash=hash_password(settings.bootstrap_analyst_password),
                    role="analyst", full_name="Investigating Officer"))
        db.commit()


def current_user(token: Annotated[str | None, Depends(oauth2)], db: Annotated[Session, Depends(get_session)]) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


def require_role(min_role: str):
    def dep(user: Annotated[User, Depends(current_user)]) -> User:
        if ROLE_RANK.get(user.role, -1) < ROLE_RANK[min_role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role {min_role}")
        return user
    return dep


def audit(db: Session, user: User | str, action: str, detail: str = "", request: Request | None = None) -> None:
    ip = request.client.host if request and request.client else ""
    db.add(AuditLog(username=user if isinstance(user, str) else user.username, action=action, detail=detail[:2000], ip=ip))
    db.commit()
