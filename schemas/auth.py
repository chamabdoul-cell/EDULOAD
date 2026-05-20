from pydantic import BaseModel, field_validator


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    role: str = "researcher"
    institution_id: int | None = None

    @field_validator("role")
    @classmethod
    def role_must_be_valid(cls, v: str) -> str:
        if v not in {"admin", "researcher", "student"}:
            raise ValueError("role must be admin, researcher, or student")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginResponse(TokenResponse):
    refresh_token: str
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    institution_id: int | None
    created_at: str | None
