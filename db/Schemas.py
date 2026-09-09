"""
schemas.py

Pydantic models defining the shape of request/response bodies.
"""

from datetime import datetime

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


class ReservationCreateRequest(BaseModel):
    mysterybox_id: int


class ReservationResponse(BaseModel):
    reservation_id: int
    mysterybox_id: int
    qr_code: str
    status: str
    reserved_at: datetime
    amount: float


class ClaimRequest(BaseModel):
    qr_code: str


class ClaimResponse(BaseModel):
    reservation_id: int
    status: str
    claimed_at: datetime
    message: str
