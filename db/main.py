"""
main.py

FastAPI entrypoint for the BlindBox Eco backend.
Handles: DB session wiring, health check, register/login,
SmartStock prediction flow, and EcoTracker stats.
"""

import os
from datetime import datetime, timedelta

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy import text, func
from sqlalchemy.orm import Session

from database import get_db
from models import Store, Reservation, MysteryBox, StockPrediction, EcoTracker, User
from Schemas import RegisterRequest, LoginRequest, AuthResponse
from Auth import hash_password, verify_password, create_access_token, decode_access_token

load_dotenv()

ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://localhost:8001")

app = FastAPI(title="BlindBox Eco API")

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Reads the JWT from the Authorization header (Bearer <token>),
    decodes it, and returns the matching User. Raises 401 if the
    token is missing, invalid, expired, or the user no longer exists.
    """
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")

    return user


@app.get("/")
def read_root():
    return {"status": "ok"}


@app.get("/db-check")
def db_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database unreachable: {exc}")
    return {"database": "connected"}


@app.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email is already registered")

    if payload.role not in ("customer", "merchant"):
        raise HTTPException(status_code=400, detail="role must be 'customer' or 'merchant'")

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.flush()

    if payload.role == "customer":
        db.add(EcoTracker(user_id=user.id, total_savings=0, total_co2_saved=0, boxes_claimed=0))

    db.commit()
    db.refresh(user)

    token = create_access_token(user_id=user.id, role=user.role)
    return AuthResponse(access_token=token, user_id=user.id, name=user.name, role=user.role)


@app.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user_id=user.id, role=user.role)
    return AuthResponse(access_token=token, user_id=user.id, name=user.name, role=user.role)


def compute_open_time_hours(opening_time) -> float:
    now = datetime.utcnow()
    opened_at_today = now.replace(
        hour=opening_time.hour, minute=opening_time.minute, second=0, microsecond=0
    )
    delta_hours = (now - opened_at_today).total_seconds() / 3600
    return max(0.0, round(delta_hours, 2))


def compute_previous_sales(db: Session, store_id: int) -> float:
    window_end = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    window_start = window_end - timedelta(days=7)

    total_claimed = (
        db.query(func.count(Reservation.id))
        .join(MysteryBox, Reservation.mysterybox_id == MysteryBox.id)
        .filter(
            MysteryBox.store_id == store_id,
            Reservation.status == "claimed",
            Reservation.claimed_at >= window_start,
            Reservation.claimed_at < window_end,
        )
        .scalar()
    )
    total_claimed = total_claimed or 0
    return round(total_claimed / 7, 2)


@app.get("/predict-stock/{store_id}")
async def predict_stock(store_id: int, db: Session = Depends(get_db)):
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail=f"Store {store_id} not found")

    open_time_hours = compute_open_time_hours(store.opening_time)
    previous_sales = compute_previous_sales(db, store_id)
    day = datetime.utcnow().strftime("%A")

    url = (
        f"{ML_SERVICE_URL}/predict/{store_id}"
        f"?open_time_hours={open_time_hours}&previous_sales={previous_sales}&day={day}"
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"ML service unreachable: {exc}")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"ML service returned an error: {exc.response.status_code}",
        )

    result = response.json()

    prediction_record = StockPrediction(
        store_id=store_id,
        predicted_quantity=result["predicted_quantity"],
        prediction_date=datetime.utcnow(),
        model_version=result.get("model_version", "unknown"),
    )
    db.add(prediction_record)
    db.commit()

    return {
        **result,
        "open_time_hours_used": open_time_hours,
        "previous_sales_used": previous_sales,
        "day_used": day,
    }


def _eco_tracker_response(user_id: int, db: Session):
    tracker = db.query(EcoTracker).filter(EcoTracker.user_id == user_id).first()
    if not tracker:
        return {"user_id": user_id, "total_savings": 0, "total_co2_saved": 0, "boxes_claimed": 0}
    return {
        "user_id": user_id,
        "total_savings": float(tracker.total_savings),
        "total_co2_saved": float(tracker.total_co2_saved),
        "boxes_claimed": tracker.boxes_claimed,
    }


@app.get("/eco-tracker/me")
def get_my_eco_tracker(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the logged-in user's EcoTracker stats, identified from
    their JWT token — no user_id needed in the URL or tracked
    manually by the app.
    """
    return _eco_tracker_response(current_user.id, db)


@app.get("/eco-tracker/{user_id}")
def get_eco_tracker(user_id: int, db: Session = Depends(get_db)):
    """
    Kept for backend/admin use. The mobile app should use
    GET /eco-tracker/me instead.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return _eco_tracker_response(user_id, db)
