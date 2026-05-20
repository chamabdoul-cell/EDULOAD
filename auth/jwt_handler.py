from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError

from config.settings import AIConfig

_ALGORITHM = "HS256"


def create_access_token(data: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=AIConfig.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({**data, "exp": expire, "type": "access"}, AIConfig.SECRET_KEY, algorithm=_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=AIConfig.REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode({**data, "exp": expire, "type": "refresh"}, AIConfig.SECRET_KEY, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, AIConfig.SECRET_KEY, algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise ValueError(str(exc)) from exc
