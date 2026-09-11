"""
Schemas.py

Pydantic models defining the shape of request/response bodies.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class UserProfileResponse(BaseModel):
    user_id: int
    name: str
    email: str
    role: str
    created_at: datetime


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
    co2_saved_kg: float


class ReservationHistoryResponse(BaseModel):
    reservation_id: int
    mysterybox_id: int

    title: str
    description: Optional[str] = None
    image_url: Optional[str] = None

    amount: float

    status: str

    reserved_at: datetime
    claimed_at: Optional[datetime] = None

    pickup_start: datetime
    pickup_end: datetime

    qr_code: str


class ClaimRequest(BaseModel):
    qr_code: str


class ClaimResponse(BaseModel):
    reservation_id: int
    status: str
    claimed_at: datetime
    message: str


class EcoTrackerUpdateRequest(BaseModel):
    savings_delta: Optional[float] = 0
    co2_delta: Optional[float] = 0
    boxes_delta: Optional[int] = 0


class EcoTrackerResponse(BaseModel):
    user_id: int
    total_savings: float
    total_co2_saved: float
    boxes_claimed: int


class PredictionResponse(BaseModel):
    store_id: int
    predicted_quantity: int


class UserUpdateRequest(BaseModel):
    """All fields optional — only send what you want to change."""

    name: Optional[str] = None
    password: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    created_at: datetime
