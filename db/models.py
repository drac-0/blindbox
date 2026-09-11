"""
models.py

SQLAlchemy ORM models matching the BlindBox Eco database schema
(Users, Stores, MysteryBoxes, Reservations, Transactions, EcoTracker,
StockPredictions).
"""

from datetime import datetime, time

from sqlalchemy import (
    Column, Integer, String, Float, Numeric, DateTime, Time, ForeignKey
)
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    store = relationship("Store", back_populates="owner", uselist=False)
    reservations = relationship("Reservation", back_populates="user")
    eco_tracker = relationship("EcoTracker", back_populates="user", uselist=False)


class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(150), nullable=False)
    address = Column(String(255))
    phone_number = Column(String(20))
    latitude = Column(Float)
    longitude = Column(Float)
    category = Column(String(50))
    opening_time = Column(Time, nullable=False, default=time(8, 0))
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="store")
    mystery_boxes = relationship("MysteryBox", back_populates="store")
    stock_predictions = relationship("StockPrediction", back_populates="store")


class MysteryBox(Base):
    __tablename__ = "mysteryboxes"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    title = Column(String(150), nullable=False)
    description = Column(String(500))
    image_url = Column(String(500))
    original_price = Column(Numeric(10, 2), nullable=False)
    discounted_price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False)
    pickup_start = Column(DateTime, nullable=False)
    pickup_end = Column(DateTime, nullable=False)
    status = Column(String(20), default="available")
    created_at = Column(DateTime, default=datetime.utcnow)

    store = relationship("Store", back_populates="mystery_boxes")
    reservations = relationship("Reservation", back_populates="mystery_box")


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    mysterybox_id = Column(Integer, ForeignKey("mysteryboxes.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    qr_code = Column(String(64), unique=True, nullable=False)
    status = Column(String(20), default="pending")
    reserved_at = Column(DateTime, default=datetime.utcnow)
    claimed_at = Column(DateTime, nullable=True)

    mystery_box = relationship("MysteryBox", back_populates="reservations")
    user = relationship("User", back_populates="reservations")
    transaction = relationship("Transaction", back_populates="reservation", uselist=False)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False, unique=True)
    amount = Column(Numeric(10, 2), nullable=False)
    method = Column(String(30))
    status = Column(String(20), default="paid")
    paid_at = Column(DateTime, default=datetime.utcnow)

    reservation = relationship("Reservation", back_populates="transaction")


class EcoTracker(Base):
    __tablename__ = "ecotracker"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    total_savings = Column(Numeric(10, 2), default=0)
    total_co2_saved = Column(Numeric(10, 2), default=0)
    boxes_claimed = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="eco_tracker")


class StockPrediction(Base):
    __tablename__ = "stockpredictions"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    predicted_quantity = Column(Integer, nullable=False)
    prediction_date = Column(DateTime, nullable=False)
    model_version = Column(String(30))
    created_at = Column(DateTime, default=datetime.utcnow)

    store = relationship("Store", back_populates="stock_predictions")
