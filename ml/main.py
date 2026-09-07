from datetime import datetime

from fastapi import FastAPI, Query

from model import SmartStockModel

app = FastAPI(title="BlindBox Eco ML Service")

model = SmartStockModel(csv_path="smartstock_synthetic_data.csv")


@app.get("/")
def read_root():
    return {"status": "ok"}


@app.get("/predict/{store_id}")
def predict(
    store_id: int,
    open_time_hours: float = Query(..., description="Hours the store has been open"),
    previous_sales: float = Query(..., description="Previous day's sales for this store"),
    day: str = Query(None, description="Day of week, e.g. 'Monday'. Defaults to today."),
):
    if day is None:
        day = datetime.utcnow().strftime("%A")

    predicted_quantity = model.predict(
        open_time_hours=open_time_hours,
        previous_sales=previous_sales,
        day=day,
    )

    return {
        "store_id": store_id,
        "predicted_quantity": predicted_quantity,
        "model_version": "linreg-v1",
    }
