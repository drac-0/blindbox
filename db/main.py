"""
main.py

FastAPI entrypoint for the BlindBox Eco backend.
Handles: DB session wiring, health check, register/login,
SmartStock prediction, EcoTracker stats, and QuickClaim
(reservation creation + pickup redemption).
"""

import os
import random
import string
from datetime import datetime, timedelta

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy import text, func, update
from sqlalchemy.orm import Session

from database import get_db
from models import Store, Reservation, MysteryBox, StockPrediction, EcoTracker, User, Transaction
from Schemas import (
    RegisterRequest, LoginRequest, AuthResponse,
    ReservationCreateRequest, ReservationResponse, ClaimRequest, ClaimResponse,
)
from Auth import hash_password, verify_password, create_access_token, decode_access_token

load_dotenv()

ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://localhost:8001")

app = FastAPI(title="BlindBox Eco API")

bearer_scheme = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),) -> User:
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
    return _eco_tracker_response(current_user.id, db)


@app.get("/eco-tracker/{user_id}")
def get_eco_tracker(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return _eco_tracker_response(user_id, db)


def _random_qr_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=12))


@app.post("/reservations", response_model=ReservationResponse)
def create_reservation(
    payload: ReservationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Creates a reservation for a mystery box (QuickClaim's "instant
    reservation" step). Quantity is decremented atomically in a single
    UPDATE statement guarded by `quantity > 0`, so two simultaneous
    requests for the last unit can't both succeed — the database
    itself serializes concurrent writes to the same row, and only one
    UPDATE will actually match and decrement; the other gets rowcount
    0 and is rejected.
    """
    box = db.query(MysteryBox).filter(MysteryBox.id == payload.mysterybox_id).first()
    if not box:
        raise HTTPException(status_code=404, detail="Mystery box not found")

    if box.status != "available":
        raise HTTPException(status_code=409, detail="This mystery box is no longer available")

    if datetime.utcnow() > box.pickup_end:
        raise HTTPException(status_code=409, detail="This mystery box's pickup window has ended")

    # Atomic check-and-decrement: prevents double-claiming the last unit
    result = db.execute(
        update(MysteryBox)
        .where(MysteryBox.id == box.id, MysteryBox.quantity > 0)
        .values(quantity=MysteryBox.quantity - 1)
    )
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="This mystery box just sold out")

    reservation = Reservation(
        mysterybox_id=box.id,
        user_id=current_user.id,
        qr_code=_random_qr_code(),
        status="pending",
        reserved_at=datetime.utcnow(),
    )
    db.add(reservation)
    db.flush()  # get reservation.id

    db.add(Transaction(
        reservation_id=reservation.id,
        amount=box.discounted_price,
        method="app",
        status="paid",
    ))

    db.commit()
    db.refresh(reservation)

    return ReservationResponse(
        reservation_id=reservation.id,
        mysterybox_id=box.id,
        qr_code=reservation.qr_code,
        status=reservation.status,
        reserved_at=reservation.reserved_at,
        amount=float(box.discounted_price),
    )


@app.post("/reservations/claim", response_model=ClaimResponse)
def claim_reservation(payload: ClaimRequest, db: Session = Depends(get_db)):
    """
    Redeems a reservation at pickup by scanning its QR code
    (QuickClaim's "penukaran pesanan via kode QR" step). Marks the
    reservation as claimed and updates the customer's EcoTracker.

    No auth required here deliberately — this is meant to be called
    from the merchant's side scanning the customer's QR code, not
    from the customer's own logged-in session.
    """
    reservation = db.query(Reservation).filter(Reservation.qr_code == payload.qr_code).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Invalid QR code")

    if reservation.status == "claimed":
        raise HTTPException(status_code=409, detail="This reservation was already claimed")

    if reservation.status == "expired":
        raise HTTPException(status_code=409, detail="This reservation has expired")

    box = db.query(MysteryBox).filter(MysteryBox.id == reservation.mysterybox_id).first()

    reservation.status = "claimed"
    reservation.claimed_at = datetime.utcnow()

    tracker = db.query(EcoTracker).filter(EcoTracker.user_id == reservation.user_id).first()
    if tracker and box:
        savings = float(box.original_price) - float(box.discounted_price)
        tracker.total_savings = float(tracker.total_savings) + savings
        tracker.boxes_claimed += 1
        # total_co2_saved intentionally left untouched here — no real
        # calculation exists yet (known gap, flagged earlier)

    db.commit()
    db.refresh(reservation)

    return ClaimResponse(
        reservation_id=reservation.id,
        status=reservation.status,
        claimed_at=reservation.claimed_at,
        message="Reservation successfully claimed",
    )
