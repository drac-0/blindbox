"""
food_data.py

Rough weight estimates (in kg) per item, used to estimate CO2 saved
when a food rescue happens. This is an ESTIMATE for demo purposes,
not a verified figure for these specific products.

Basis: food waste sent to landfill decomposes anaerobically and
produces methane, a much more potent greenhouse gas than CO2. A
commonly cited approximate factor in food-waste sustainability
literature is that every kg of food rescued from waste avoids
roughly 2.5 kg of CO2-equivalent emissions. This is a simplification
used across many consumer-facing food rescue apps (e.g. Too Good To
Go uses a similar approach) — real precision would require a
lifecycle analysis specific to each food type, which is out of scope
here.
"""

CO2E_PER_KG_FOOD_SAVED = 2.5  # kg CO2-equivalent avoided per kg of food rescued

# Estimated serving weight per item (kg). Matches the item titles used
# in seed.py's ITEMS_BY_CATEGORY.
ITEM_WEIGHT_KG = {
    "Croissant Coklat": 0.08,
    "Roti Sobek Keju": 0.25,
    "Donat Gula": 0.06,
    "Kue Lapis Legit": 0.15,
    "Brownies Panggang": 0.12,
    "Es Kopi Susu": 0.35,
    "Cappuccino": 0.25,
    "Croffle Original": 0.12,
    "Sandwich Panggang": 0.20,
    "Kue Cubit Coklat": 0.10,
    "Nasi Goreng Spesial": 0.35,
    "Ayam Geprek": 0.30,
    "Mie Ayam": 0.35,
    "Rendang Nasi Padang": 0.40,
    "Sate Ayam": 0.25,
}

FALLBACK_WEIGHT_KG = 0.20  # used for any item title not in the map above


def estimate_co2_saved_kg(item_title: str) -> float:
    """
    Estimated kg of CO2-equivalent avoided by rescuing one unit of
    this item instead of it going to waste.
    """
    weight = ITEM_WEIGHT_KG.get(item_title, FALLBACK_WEIGHT_KG)
    return round(weight * CO2E_PER_KG_FOOD_SAVED, 2)
