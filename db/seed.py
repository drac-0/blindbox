"""
seed.py

Creates all tables (if they don't exist) and fills the database with
synthetic data across every table in the schema: users, stores,
mysteryboxes, reservations, transactions, ecotracker, stockpredictions.

This is FAKE data for testing purposes only. Run once against a fresh
database:

    python seed.py
"""

import random
import string
from datetime import datetime, timedelta, time

from database import Base, engine, SessionLocal
from models import (
    User, Store, MysteryBox, Reservation, Transaction,
    EcoTracker, StockPrediction,
)

# Create all tables based on models.py
Base.metadata.create_all(bind=engine)

db = SessionLocal()

# --- Config ---
N_MERCHANTS = 8
N_CUSTOMERS = 20
BOXES_PER_STORE = 5
GUARANTEED_YESTERDAY_RESERVATIONS_PER_STORE = 2  # ensures previous_sales is never 0 right after seeding
CATEGORIES = ["Bakery", "Cafe", "Restaurant"]
STORE_NAMES = [
    "Roti Segar", "Kopi Senja", "Warung Padang Berkah", "Bakery Manis",
    "Cafe Embun", "Nasi Kotak Sejahtera", "Toko Kue Bahagia", "Kedai Kopi Pagi",
]
CUSTOMER_NAMES = [
    "Andi", "Budi", "Citra", "Dewi", "Eka", "Fajar", "Gita", "Hadi",
    "Indah", "Joko", "Kartika", "Lina", "Made", "Nia", "Oki", "Putri",
    "Rian", "Sari", "Tono", "Umi",
]


def random_qr_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=12))


def random_opening_time():
    # Varies each store's opening hour so SmartStock predictions differ
    # meaningfully between stores instead of all using the same default.
    return time(random.randint(6, 10), random.choice([0, 15, 30, 45]))


def yesterday_random_time():
    yesterday = datetime.utcnow() - timedelta(days=1)
    return yesterday.replace(
        hour=random.randint(8, 20), minute=random.randint(0, 59),
        second=0, microsecond=0,
    )


try:
    # --- Users: merchants + customers ---
    merchants = []
    for i in range(N_MERCHANTS):
        user = User(
            name=f"Merchant {i+1}",
            email=f"merchant{i+1}@example.com",
            password_hash="fakehash",  # placeholder; real auth not built yet
            role="merchant",
        )
        db.add(user)
        merchants.append(user)

    customers = []
    for name in CUSTOMER_NAMES[:N_CUSTOMERS]:
        user = User(
            name=name,
            email=f"{name.lower()}@example.com",
            password_hash="fakehash",
            role="customer",
        )
        db.add(user)
        customers.append(user)

    db.flush()  # assigns IDs without committing yet

    # --- Stores: one per merchant, each with a varied opening time ---
    stores = []
    for i, merchant in enumerate(merchants):
        store = Store(
            user_id=merchant.id,
            name=STORE_NAMES[i % len(STORE_NAMES)],
            address=f"Jl. Contoh No. {random.randint(1, 100)}, Padang",
            latitude=-0.95 + random.uniform(-0.05, 0.05),   # roughly around Padang
            longitude=100.35 + random.uniform(-0.05, 0.05),
            category=random.choice(CATEGORIES),
            opening_time=random_opening_time(),
        )
        db.add(store)
        stores.append(store)

    db.flush()

    # --- Mystery boxes: a few per store ---
    boxes = []
    for store in stores:
        for _ in range(BOXES_PER_STORE):
            original_price = round(random.uniform(20000, 80000), -2)  # rupiah-ish
            discount = random.choice([0.3, 0.4, 0.5])
            box = MysteryBox(
                store_id=store.id,
                title=f"Mystery Box {store.name}",
                description="Paket kejutan sisa makanan hari ini",
                original_price=original_price,
                discounted_price=round(original_price * (1 - discount), -2),
                quantity=random.randint(1, 10),
                pickup_start=datetime.utcnow().replace(hour=18, minute=0),
                pickup_end=datetime.utcnow().replace(hour=20, minute=0),
                status="available",
            )
            db.add(box)
            boxes.append(box)

    db.flush()

    # --- EcoTracker: one per customer, starts at zero ---
    for customer in customers:
        db.add(EcoTracker(
            user_id=customer.id,
            total_savings=0,
            total_co2_saved=0,
            boxes_claimed=0,
        ))

    db.flush()

    def create_reservation_and_transaction(box, customer, claimed_at):
        reservation = Reservation(
            mysterybox_id=box.id,
            user_id=customer.id,
            qr_code=random_qr_code(),
            status="claimed",
            reserved_at=claimed_at - timedelta(minutes=random.randint(5, 60)),
            claimed_at=claimed_at,
        )
        db.add(reservation)
        db.flush()  # get reservation.id

        db.add(Transaction(
            reservation_id=reservation.id,
            amount=box.discounted_price,
            method=random.choice(["e-wallet", "bank_transfer", "cash"]),
            status="paid",
        ))

        tracker = db.query(EcoTracker).filter_by(user_id=customer.id).first()
        savings = box.original_price - box.discounted_price
        tracker.total_savings = float(tracker.total_savings) + float(savings)
        tracker.total_co2_saved = float(tracker.total_co2_saved) + round(random.uniform(0.5, 2.0), 2)
        tracker.boxes_claimed += 1

    total_reservations = 0

    # --- Guaranteed reservations: every store gets some claimed 'yesterday' ---
    # This ensures previous_sales is never 0 for every store right after a
    # fresh seed, instead of depending on random luck to land in that window.
    for store in stores:
        store_boxes = [b for b in boxes if b.store_id == store.id]
        for _ in range(GUARANTEED_YESTERDAY_RESERVATIONS_PER_STORE):
            box = random.choice(store_boxes)
            customer = random.choice(customers)
            create_reservation_and_transaction(box, customer, yesterday_random_time())
            total_reservations += 1

    # --- Additional random reservations across the last few days, for variety ---
    n_extra_reservations = min(20, len(boxes) * 2)
    for _ in range(n_extra_reservations):
        box = random.choice(boxes)
        customer = random.choice(customers)
        claimed_at = datetime.utcnow() - timedelta(hours=random.randint(1, 96))
        create_reservation_and_transaction(box, customer, claimed_at)
        total_reservations += 1

    # --- Stock predictions: one per store, using the stub model ---
    for store in stores:
        db.add(StockPrediction(
            store_id=store.id,
            predicted_quantity=random.randint(0, 20),
            prediction_date=datetime.utcnow(),
            model_version="stub-v0",
        ))

    db.commit()
    print(f"Seeded: {len(merchants)} merchants, {len(customers)} customers, "
          f"{len(stores)} stores (each with a varied opening_time), "
          f"{len(boxes)} mystery boxes, "
          f"{total_reservations} reservations with transactions "
          f"({GUARANTEED_YESTERDAY_RESERVATIONS_PER_STORE} per store guaranteed 'yesterday'), "
          f"{len(customers)} eco-tracker records, {len(stores)} stock predictions.")

except Exception as e:
    db.rollback()
    print(f"Seeding failed, rolled back: {e}")
    raise
finally:
    db.close()
