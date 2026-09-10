"""
refresh_availability.py

Resets every item's pickup window to start now and end N hours from
now, and tops quantity back up if it's run low from testing. Use this
right before a demo/pitch to guarantee items show up in /items,
WITHOUT wiping users, reservations, or transaction history like a
full reseed would.

Run with:
    python refresh_availability.py
"""

import random
from datetime import datetime, timedelta

from database import SessionLocal
from models import MysteryBox

HOURS_WINDOW = 24          # how far into the future pickup_end should be
MIN_QUANTITY_TOPUP = 3     # ensure every item has at least this many left

db = SessionLocal()

try:
    boxes = db.query(MysteryBox).all()
    now = datetime.utcnow()

    for box in boxes:
        box.pickup_start = now
        box.pickup_end = now + timedelta(hours=HOURS_WINDOW)
        box.status = "available"
        if box.quantity < MIN_QUANTITY_TOPUP:
            box.quantity = random.randint(MIN_QUANTITY_TOPUP, MIN_QUANTITY_TOPUP + 5)

    db.commit()
    print(f"Refreshed {len(boxes)} items: pickup window now {now} to {now + timedelta(hours=HOURS_WINDOW)}.")

except Exception as e:
    db.rollback()
    print(f"Refresh failed, rolled back: {e}")
    raise
finally:
    db.close()
