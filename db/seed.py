"""
seed.py

Creates all tables (if they don't exist) and fills the database with
synthetic data across every table in the schema: users, stores
(with both an address and a separate phone_number), mysteryboxes
(real food/beverage items), reservations, ecotracker, stockpredictions.

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

Base.metadata.create_all(bind=engine)

db = SessionLocal()

# --- Config ---
N_MERCHANTS = 8
N_CUSTOMERS = 20
BOXES_PER_STORE = 5
GUARANTEED_YESTERDAY_RESERVATIONS_PER_STORE = 2
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

ITEMS_BY_CATEGORY = {
    "Bakery": [
        ("Croissant Coklat", "Croissant renyah dengan isian coklat lumer"),
        ("Roti Sobek Keju", "Roti empuk dengan taburan keju di atasnya"),
        ("Donat Gula", "Donat klasik bertabur gula halus"),
        ("Kue Lapis Legit", "Kue lapis dengan rempah khas, dipotong per slice"),
        ("Brownies Panggang", "Brownies coklat padat, dipanggang hari ini"),
    ],
    "Cafe": [
        ("Es Kopi Susu", "Kopi susu dingin, sisa seduhan hari ini"),
        ("Cappuccino", "Cappuccino dengan foam lembut"),
        ("Croffle Original", "Croissant waffle renyah, disajikan hangat"),
        ("Sandwich Panggang", "Sandwich isi telur dan sayur, dipanggang"),
        ("Kue Cubit Coklat", "Kue cubit lembut dengan topping coklat"),
    ],
    "Restaurant": [
        ("Nasi Goreng Spesial", "Nasi goreng dengan telur dan ayam suwir"),
        ("Ayam Geprek", "Ayam goreng geprek dengan sambal bawang"),
        ("Mie Ayam", "Mie ayam dengan pangsit dan bakso"),
        ("Rendang Nasi Padang", "Nasi padang dengan rendang daging sapi"),
        ("Sate Ayam", "Sate ayam dengan bumbu kacang, per porsi"),
    ],
}

INDONESIAN_MOBILE_PREFIXES = [
    "811", "812", "813", "821", "822", "823",
    "814", "815", "816", "855", "856", "857", "858",
    "817", "818", "819", "859", "877", "878",
    "895", "896", "897", "898", "899",
    "881", "882", "883", "884", "885", "886", "887", "888", "889",
]


def random_qr_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=12))


def random_opening_time():
    return time(random.randint(6, 10), random.choice([0, 15, 30, 45]))


def yesterday_random_time():
    yesterday = datetime.utcnow() - timedelta(days=1)
    return yesterday.replace(
        hour=random.randint(8, 20), minute=random.randint(0, 59),
        second=0, microsecond=0,
    )


def random_indonesian_phone() -> str:
    prefix = random.choice(INDONESIAN_MOBILE_PREFIXES)
    part1 = f"{random.randint(0, 9999):04d}"
    part2 = f"{random.randint(0, 9999):04d}"
    return f"+62 {prefix}-{part1}-{part2}"


def random_padang_address() -> str:
    streets = [
        "Jl. Khatib Sulaiman", "Jl. Veteran", "Jl. Sudirman",
        "Jl. Hamka", "Jl. Ahmad Yani", "Jl. Diponegoro",
        "Jl. Gajah Mada", "Jl. Bundo Kanduang", "Jl. Damar",
    ]
    street = random.choice(streets)
    number = random.randint(1, 150)
    return f"{street} No. {number}, Padang"


try:
    # --- Users ---
    merchants = []
    for i in range(N_MERCHANTS):
        user = User(
            name=f"Merchant {i+1}",
            email=f"merchant{i+1}@example.com",
            password_hash="fakehash",
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

    db.flush()

    # --- Stores: real street address AND a separate phone number ---
    stores = []
    for i, merchant in enumerate(merchants):
        store = Store(
            user_id=merchant.id,
            name=STORE_NAMES[i % len(STORE_NAMES)],
            address=random_padang_address(),
            phone_number=random_indonesian_phone(),
            latitude=-0.95 + random.uniform(-0.05, 0.05),
            longitude=100.35 + random.uniform(-0.05, 0.05),
            category=random.choice(CATEGORIES),
            opening_time=random_opening_time(),
        )
        db.add(store)
        stores.append(store)

    db.flush()

    # --- Items ---
    boxes = []
    for store in stores:
        item_pool = ITEMS_BY_CATEGORY[store.category]
        for _ in range(BOXES_PER_STORE):
            item_name, item_description = random.choice(item_pool)
            original_price = round(random.uniform(15000, 60000), -2)
            discount = random.choice([0.3, 0.4, 0.5])
            box = MysteryBox(
                store_id=store.id,
                title=item_name,
                description=item_description,
                original_price=original_price,
                discounted_price=round(original_price * (1 - discount), -2),
                quantity=random.randint(1, 10),
                pickup_start=datetime.utcnow(),
                pickup_end=datetime.utcnow() + timedelta(hours=24),
                status="available",
            )
            db.add(box)
            boxes.append(box)

    db.flush()

    # --- EcoTracker ---
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
        db.flush()

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

    for store in stores:
        store_boxes = [b for b in boxes if b.store_id == store.id]
        for _ in range(GUARANTEED_YESTERDAY_RESERVATIONS_PER_STORE):
            box = random.choice(store_boxes)
            customer = random.choice(customers)
            create_reservation_and_transaction(box, customer, yesterday_random_time())
            total_reservations += 1

    n_extra_reservations = min(20, len(boxes) * 2)
    for _ in range(n_extra_reservations):
        box = random.choice(boxes)
        customer = random.choice(customers)
        claimed_at = datetime.utcnow() - timedelta(hours=random.randint(1, 96))
        create_reservation_and_transaction(box, customer, claimed_at)
        total_reservations += 1

    for store in stores:
        db.add(StockPrediction(
            store_id=store.id,
            predicted_quantity=random.randint(0, 20),
            prediction_date=datetime.utcnow(),
            model_version="stub-v0",
        ))

    db.commit()
    print(f"Seeded: {len(merchants)} merchants, {len(customers)} customers, "
          f"{len(stores)} stores (each with a real address AND a phone_number), "
          f"{len(boxes)} real food/beverage items, "
          f"{total_reservations} reservations with transactions, "
          f"{len(customers)} eco-tracker records, {len(stores)} stock predictions.")

except Exception as e:
    db.rollback()
    print(f"Seeding failed, rolled back: {e}")
    raise
finally:
    db.close()
