"""
schemas.py

Pydantic models defining the shape of request/response bodies for
the API (currently just auth; can grow as more endpoints are added).
"""

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str  # "customer" or "merchant"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    name: str
    role: str
