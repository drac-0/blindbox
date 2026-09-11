"""
main.py

FastAPI entrypoint for the BlindBox Eco backend.
Handles: DB session wiring, health check, register/login, user
profile, item listing + detail, SmartStock prediction, EcoTracker
(read + update), and QuickClaim (reservation + pickup redemption).

Note on payment: there is no payment gateway integration. A
successful reservation IS the "payment" — it immediately records the
money saved and estimated CO2 saved into the user's EcoTracker. No
separate Transaction/payment step exists.
"""

import math
import os
import random
import string
from datetime import datetime, timedelta
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy import text, func, update
from sqlalchemy.orm import Session

from database import get_db
from models import Store, Reservation, MysteryBox, StockPrediction, EcoTracker, User
from Schemas import (
    RegisterRequest, LoginRequest, AuthResponse,
    ReservationCreateRequest, ReservationResponse, ClaimRequest, ClaimResponse,
    EcoTrackerUpdateRequest, EcoTrackerResponse, PredictionResponse,
    UserProfileResponse, UserUpdateRequest,
)
from Auth import hash_password, verify_password, create_access_token, decode_access_token
from food_data import estimate_co2_saved_kg

load_dotenv()

ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://localhost:8001")

app = FastAPI(title="BlindBox Eco API")

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
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


@app.get("/users/me", response_model=UserProfileResponse)
def get_my_profile(current_user: User = Depends(get_current_user)):
    """
    Returns the logged-in user's profile — identified from their JWT
    token, same pattern as /eco-tracker/me. No user_id needed in the
    URL.
    """
    return UserProfileResponse(
        user_id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        role=current_user.role,
        created_at=current_user.created_at,
    )


@app.patch("/users/me", response_model=UserProfileResponse)
def update_my_profile(
    payload: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Updates the logged-in user's name and/or password. Both fields
    optional — only send what you want to change. Email is
    deliberately not editable here to avoid uniqueness-conflict
    handling within today's timeline.
    """
    if payload.name is not None:
        current_user.name = payload.name

    if payload.password is not None:
        current_user.password_hash = hash_password(payload.password)

    db.commit()
    db.refresh(current_user)

    return UserProfileResponse(
        user_id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        role=current_user.role,
        created_at=current_user.created_at,
    )


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _serialize_item(box: MysteryBox, store: Store, user_lat: Optional[float], user_lng: Optional[float]) -> dict:
    distance_km = None
    if user_lat is not None and user_lng is not None and store.latitude is not None and store.longitude is not None:
        distance_km = round(haversine_km(user_lat, user_lng, store.latitude, store.longitude), 2)

    minutes_left = None
    now = datetime.utcnow()
    if box.pickup_end > now:
        minutes_left = int((box.pickup_end - now).total_seconds() / 60)

    return {
        "item_id": box.id,
        "title": box.title,
        "description": box.description,
        "image_url": box.image_url,
        "original_price": float(box.original_price),
        "discounted_price": float(box.discounted_price),
        "quantity_available": box.quantity,
        "pickup_start": box.pickup_start,
        "pickup_end": box.pickup_end,
        "minutes_left": minutes_left,
        "store": {
            "store_id": store.id,
            "name": store.name,
            "address": store.address,
            "phone_number": store.phone_number,
            "category": store.category,
            "latitude": store.latitude,
            "longitude": store.longitude,
        },
        "distance_km": distance_km,
    }


@app.get("/items")
def list_items(
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    boxes = (
        db.query(MysteryBox)
        .filter(
            MysteryBox.status == "available",
            MysteryBox.quantity > 0,
            MysteryBox.pickup_end > now,
        )
        .all()
    )

    items = []
    for box in boxes:
        store = db.query(Store).filter(Store.id == box.store_id).first()
        if not store:
            continue
        items.append(_serialize_item(box, store, lat, lng))

    if lat is not None and lng is not None:
        items.sort(key=lambda i: (i["distance_km"] if i["distance_km"] is not None else float("inf")))

    return {"count": len(items), "items": items}


@app.get("/items/{item_id}")
def get_item(
    item_id: int,
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    db: Session = Depends(get_db),
):
    box = db.query(MysteryBox).filter(MysteryBox.id == item_id).first()
    if not box:
        raise HTTPException(status_code=404, detail="Item not found")

    store = db.query(Store).filter(Store.id == box.store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store for this item not found")

    return _serialize_item(box, store, lat, lng)


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


@app.get("/predict-stock/{store_id}", response_model=PredictionResponse)
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

    return PredictionResponse(store_id=store_id, predicted_quantity=result["predicted_quantity"])


def _eco_tracker_response(user_id: int, db: Session) -> EcoTrackerResponse:
    tracker = db.query(EcoTracker).filter(EcoTracker.user_id == user_id).first()
    if not tracker:
        return EcoTrackerResponse(user_id=user_id, total_savings=0, total_co2_saved=0, boxes_claimed=0)
    return EcoTrackerResponse(
        user_id=user_id,
        total_savings=float(tracker.total_savings),
        total_co2_saved=float(tracker.total_co2_saved),
        boxes_claimed=tracker.boxes_claimed,
    )


@app.get("/eco-tracker/me", response_model=EcoTrackerResponse)
def get_my_eco_tracker(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _eco_tracker_response(current_user.id, db)


@app.patch("/eco-tracker/me", response_model=EcoTrackerResponse)
def update_my_eco_tracker(
    payload: EcoTrackerUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tracker = db.query(EcoTracker).filter(EcoTracker.user_id == current_user.id).first()

    if not tracker:
        tracker = EcoTracker(user_id=current_user.id, total_savings=0, total_co2_saved=0, boxes_claimed=0)
        db.add(tracker)
        db.flush()

    tracker.total_savings = float(tracker.total_savings) + (payload.savings_delta or 0)
    tracker.total_co2_saved = float(tracker.total_co2_saved) + (payload.co2_delta or 0)
    tracker.boxes_claimed = tracker.boxes_claimed + (payload.boxes_delta or 0)

    db.commit()
    db.refresh(tracker)

    return _eco_tracker_response(current_user.id, db)


@app.get("/eco-tracker/{user_id}", response_model=EcoTrackerResponse)
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
    box = db.query(MysteryBox).filter(MysteryBox.id == payload.mysterybox_id).first()
    if not box:
        raise HTTPException(status_code=404, detail="Item not found")

    if box.status != "available":
        raise HTTPException(status_code=409, detail="This item is no longer available")

    if datetime.utcnow() > box.pickup_end:
        raise HTTPException(status_code=409, detail="This item's pickup window has ended")

    result = db.execute(
        update(MysteryBox)
        .where(MysteryBox.id == box.id, MysteryBox.quantity > 0)
        .values(quantity=MysteryBox.quantity - 1)
    )
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="This item just sold out")

    reservation = Reservation(
        mysterybox_id=box.id,
        user_id=current_user.id,
        qr_code=_random_qr_code(),
        status="pending",  # awaiting pickup confirmation — EcoTracker is NOT updated yet
        reserved_at=datetime.utcnow(),
    )
    db.add(reservation)
    db.flush()

    # Preview values only — shown to the user now so they know what
    # they'll earn, but NOT yet applied to EcoTracker. That happens in
    # /reservations/claim, once pickup is actually confirmed.
    savings = float(box.original_price) - float(box.discounted_price)
    co2_saved = estimate_co2_saved_kg(box.title)

    db.commit()
    db.refresh(reservation)

    return ReservationResponse(
        reservation_id=reservation.id,
        mysterybox_id=box.id,
        qr_code=reservation.qr_code,
        status=reservation.status,
        reserved_at=reservation.reserved_at,
        amount=float(box.discounted_price),
        co2_saved_kg=co2_saved,
    )


@app.post("/reservations/claim", response_model=ClaimResponse)
def claim_reservation(payload: ClaimRequest, db: Session = Depends(get_db)):
    """
    Confirms pickup (step 3 of the flow: reserve -> wait -> confirm
    pickup). This is the point where the database actually reflects
    a completed food rescue — EcoTracker (savings, CO2, boxes_claimed)
    is updated HERE, not at reservation time, since the order isn't
    truly complete until pickup is confirmed.
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

    if box:
        savings = float(box.original_price) - float(box.discounted_price)
        co2_saved = estimate_co2_saved_kg(box.title)

        tracker = db.query(EcoTracker).filter(EcoTracker.user_id == reservation.user_id).first()
        if not tracker:
            tracker = EcoTracker(user_id=reservation.user_id, total_savings=0, total_co2_saved=0, boxes_claimed=0)
            db.add(tracker)
            db.flush()

        tracker.total_savings = float(tracker.total_savings) + savings
        tracker.total_co2_saved = float(tracker.total_co2_saved) + co2_saved
        tracker.boxes_claimed += 1

    db.commit()
    db.refresh(reservation)

    return ClaimResponse(
        reservation_id=reservation.id,
        status=reservation.status,
        claimed_at=reservation.claimed_at,
        message="Reservation successfully claimed",
    )

@app.get("/users/{user_id}", response_model=UserResponse, tags=["Users"])
def get_user_profile(
    user_id: int,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User tidak ditemukan",
        )

    return user


@app.get("/users/me", response_model=UserResponse, tags=["Users"])
def get_user_profile(
    current_user: User = Depends(get_current_user),
):
    return current_user
