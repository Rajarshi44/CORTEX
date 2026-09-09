from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import audit, create_token, current_user, hash_password, require_role, verify_password
from ..db import AuditLog, User, get_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


class UserOut(BaseModel):
    username: str
    role: str
    full_name: str


class CreateUser(BaseModel):
    username: str
    password: str
    role: str = "analyst"
    full_name: str = ""


@router.post("/login")
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: Annotated[Session, Depends(get_session)], request: Request):
    user = db.query(User).filter(User.username == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        audit(db, form.username, "login_failed", request=request)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    audit(db, user, "login", request=request)
    return {"access_token": create_token(user), "token_type": "bearer",
            "user": UserOut(username=user.username, role=user.role, full_name=user.full_name)}


@router.get("/me", response_model=UserOut)
def me(user: Annotated[User, Depends(current_user)]):
    return UserOut(username=user.username, role=user.role, full_name=user.full_name)


@router.post("/users", response_model=UserOut, dependencies=[Depends(require_role("admin"))])
def create_user(body: CreateUser, db: Annotated[Session, Depends(get_session)], admin: Annotated[User, Depends(current_user)]):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(400, "Username exists")
    u = User(username=body.username, password_hash=hash_password(body.password), role=body.role, full_name=body.full_name)
    db.add(u)
    db.commit()
    audit(db, admin, "create_user", body.username)
    return UserOut(username=u.username, role=u.role, full_name=u.full_name)


@router.get("/audit", dependencies=[Depends(require_role("admin"))])
def audit_log(db: Annotated[Session, Depends(get_session)], limit: int = 200):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [{"id": r.id, "user": r.username, "action": r.action, "detail": r.detail, "ip": r.ip, "at": r.created_at.isoformat()} for r in rows]
