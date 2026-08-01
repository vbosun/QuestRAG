from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    id_number: str = Field(..., min_length=32)  # SM2-encrypted hex string
    password: str = Field(..., min_length=32)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: "UserInfo"


class UserInfo(BaseModel):
    id: int
    full_name: str
    id_number_masked: str
    role: str
    roles: list[str] = []
    permissions: list[str] = []
    rag_scopes: list[str] = []


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=32)
    new_password: str = Field(..., min_length=32)
    confirm_password: str = Field(..., min_length=32)


class CurrentUser(BaseModel):
    id: int
    sid: str
    role: str
    roles: list[str] = []
    permissions: list[str] = []
    rag_scopes: list[str] = []
    status: int
    full_name: str | None = None
    id_number_masked: str | None = None
    token_version: int


class AuthErrorDetail(BaseModel):
    code: str
    message: str
