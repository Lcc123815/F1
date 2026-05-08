"""认证相关 API：登录 / 注册 / 找回密码

密码使用 sha256 摘要存储；真实生产环境应替换为 bcrypt/argon2 等。
"""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import User
from app.db.session import SessionLocal, engine, get_db

logger = logging.getLogger("auth")
logging.basicConfig(level=logging.INFO)

router = APIRouter()

# 启动时自动建表（包含新加的 users 表）
Base.metadata.create_all(bind=engine)


def _hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()


PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


# ============== 启动时确保有内置 admin 用户 ==============
def _ensure_default_user() -> None:
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "admin").first():
            db.add(
                User(
                    username="admin",
                    password_hash=_hash_password("123456"),
                    name="管理员",
                )
            )
            db.commit()
    finally:
        db.close()


_ensure_default_user()


# ============== 请求 / 响应模型 ==============
class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    phone: Optional[str] = None
    password: str = Field(..., min_length=6, max_length=20)


class ForgotPasswordRequest(BaseModel):
    username: str
    new_password: str = Field(..., min_length=6, max_length=20)


def _ok(data=None, msg="ok"):
    return {"code": 200, "msg": msg, "data": data or {}}


# ============== 接口 ==============
@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    identifier = (req.username or "").strip()
    # 同时支持 用户名 / 手机号 登录
    if PHONE_RE.match(identifier):
        user = db.query(User).filter(User.phone == identifier).first()
    else:
        user = db.query(User).filter(User.username == identifier).first()
    if not user or user.password_hash != _hash_password(req.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    token = secrets.token_hex(16)
    return _ok(
        {
            "token": token,
            "username": user.username,
            "name": user.name or user.username,
        },
        msg="登录成功",
    )


@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if req.phone and not PHONE_RE.match(req.phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确")
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=409, detail="用户名已存在")
    if req.phone and db.query(User).filter(User.phone == req.phone).first():
        raise HTTPException(status_code=409, detail="手机号已被注册")

    user = User(
        username=req.username,
        phone=req.phone,
        password_hash=_hash_password(req.password),
        name=req.username,
    )
    db.add(user)
    db.commit()
    return _ok({"username": user.username}, msg="注册成功")


@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="未找到该用户")
    user.password_hash = _hash_password(req.new_password)
    db.commit()
    return _ok(msg="密码重置成功")


@router.get("/me")
def me(token: Optional[str] = None):
    # demo 用：真实场景应解码 token 并校验
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    return _ok({"token": token})
