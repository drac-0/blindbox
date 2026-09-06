import random

from fastapi import FastAPI

app = FastAPI(title="BlindBox Eco ML Service")


@app.get("/")
def read_root():
    return {"status": "ok"}


@app.get("/predict/{store_id}")
def predict(store_id: int):
    predicted_quantity = random.randint(0, 20)

    return {
        "store_id": store_id,
        "predicted_quantity": predicted_quantity,
        "model_version": "stub-v0",
    }
