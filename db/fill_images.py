"""
fill_images.py

One-time (or re-runnable) script that fills image_url for every row
in mysteryboxes, matching each item's title to a relevant food photo.

Requires the image_url column to already exist:
    ALTER TABLE mysteryboxes ADD COLUMN image_url VARCHAR(500);

Uses LoremFlickr (https://loremflickr.com) — a free, keyword-based
placeholder image service. No API key needed. Each URL returns an
actual photo matching the keyword, not a generic random image.

Run with:
    python fill_images.py
"""

from database import SessionLocal
from models import MysteryBox

# Maps each item title (must match seed.py's ITEMS_BY_CATEGORY titles
# exactly) to an English search keyword for the image service.
IMAGE_KEYWORDS = {
    "Croissant Coklat": "croissant",
    "Roti Sobek Keju": "bread",
    "Donat Gula": "donut",
    "Kue Lapis Legit": "layer-cake",
    "Brownies Panggang": "brownie",
    "Es Kopi Susu": "iced-coffee",
    "Cappuccino": "cappuccino",
    "Croffle Original": "waffle",
    "Sandwich Panggang": "sandwich",
    "Kue Cubit Coklat": "chocolate-cake",
    "Nasi Goreng Spesial": "fried-rice",
    "Ayam Geprek": "fried-chicken",
    "Mie Ayam": "noodles",
    "Rendang Nasi Padang": "beef-rendang",
    "Sate Ayam": "satay",
}

FALLBACK_KEYWORD = "food"  # used if a title isn't in the map above

db = SessionLocal()

try:
    boxes = db.query(MysteryBox).all()
    updated = 0

    for box in boxes:
        keyword = IMAGE_KEYWORDS.get(box.title, FALLBACK_KEYWORD)
        box.image_url = f"https://loremflickr.com/400/300/{keyword}"
        updated += 1

    db.commit()
    print(f"Updated image_url for {updated} items.")

except Exception as e:
    db.rollback()
    print(f"Failed, rolled back: {e}")
    raise
finally:
    db.close()
