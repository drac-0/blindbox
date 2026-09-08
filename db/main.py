"""
main.py

FastAPI entrypoint for the BlindBox Eco backend.
Handles: DB session wiring, a health-check endpoint, and the
SmartStock prediction flow (computing real features from the
database, calling the ML service, and saving the result).
"""

import os
from datetime import datetime, timedelta

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text, func
from sqlalchemy.orm import Session

from database import get_db
from models import Store, Reservation, MysteryBox, StockPrediction, EcoTracker, User

load_dotenv()

ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://localhost:8001")

app = FastAPI(title="BlindBox Eco API")


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


def compute_open_time_hours(opening_time) -> float:
    """
    Hours since the store opened today, based on its opening_time
    column. Clamped to 0 if called before opening (shouldn't normally
    happen, but avoids a negative feature value).
    """
    now = datetime.utcnow()
    opened_at_today = now.replace(
        hour=opening_time.hour, minute=opening_time.minute, second=0, microsecond=0
    )
    delta_hours = (now - opened_at_today).total_seconds() / 3600
    return max(0.0, round(delta_hours, 2))


def compute_previous_sales(db: Session, store_id: int) -> float:
    """
    Average daily sales (claimed reservations) for this store over the
    last 7 days, ending yesterday (today is excluded since it's still
    in progress and would understate the average).

    Returns 0 if there's no history yet in that window.
    """
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

    average_per_day = total_claimed / 7
    return round(average_per_day, 2)


@app.get("/predict-stock/{store_id}")
async def predict_stock(store_id: int, db: Session = Depends(get_db)):
    """
    Computes real features from the database (hours open today,
    average daily sales over the last 7 days), calls the ML service
    for a prediction, saves the result to stockpredictions, and
    returns it.
    """
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

    # Persist the prediction so history accumulates in stockpredictions
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


@app.get("/eco-tracker/{user_id}")
def get_eco_tracker(user_id: int, db: Session = Depends(get_db)):
    """
    Returns a user's accumulated EcoTracker stats: total money saved,
    total CO2 saved, and number of boxes claimed.
 
    If the user exists but has no EcoTracker row yet (e.g. a brand new
    user who hasn't claimed anything), returns zeros instead of a 404
    so the app doesn't need special-case error handling for new users.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
 
    tracker = db.query(EcoTracker).filter(EcoTracker.user_id == user_id).first()
 
    if not tracker:
        return {
            "user_id": user_id,
            "total_savings": 0,
            "total_co2_saved": 0,
            "boxes_claimed": 0,
        }
 
    return {
        "user_id": user_id,
        "total_savings": float(tracker.total_savings),
        "total_co2_saved": float(tracker.total_co2_saved),
        "boxes_claimed": tracker.boxes_claimed,
    }

