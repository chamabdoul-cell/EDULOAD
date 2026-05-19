"""Authentication endpoints — login, register, token refresh."""
import sqlite3

from fastapi import APIRouter, HTTPException, Depends

from auth.jwt_handler import create_access_token, create_refresh_token, decode_token
from auth.password import hash_password, verify_password
from auth.dependencies import get_current_user
from schemas.auth import LoginRequest, RegisterRequest, LoginResponse, TokenResponse, RefreshRequest
from db import get_db
import repositories.users as users_repo

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    con = get_db()
    row = users_repo.get_user_by_email(con, req.email)
    con.close()

    if not row or not verify_password(req.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    data = {"sub": row["id"]}
    return LoginResponse(
        access_token=create_access_token(data),
        refresh_token=create_refresh_token(data),
        role=row["role"],
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(req: RefreshRequest):
    try:
        payload = decode_token(req.refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("Not a refresh token")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    return TokenResponse(access_token=create_access_token({"sub": payload["sub"]}))


@router.post("/register", status_code=201)
def register(req: RegisterRequest):
    con = get_db()
    try:
        users_repo.create_user(con, req.email, hash_password(req.password),
                               req.role, req.institution_id)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Email already registered")
    finally:
        con.close()
    return {"status": "registered"}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return {k: user[k] for k in ("id", "email", "role", "institution_id")}
