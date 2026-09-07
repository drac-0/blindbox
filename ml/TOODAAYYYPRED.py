"""
main.py (ML service)

SmartStock prediction service. Trains the regression once at startup
(from smartstock_synthetic_data.csv) and serves real predictions
through /predict/{store_id}.

Run with: uvicorn main:app --reload --host 0.0.0.0 --port 8001
"""

from datetime import datetime

from fastapi import FastAPI, Query

from model import SmartStockModel

app = FastAPI(title="BlindBox Eco ML Service")

# Trained once when the service starts, kept in memory for all requests
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
    """
    Real prediction using the trained linear regression model.
    open_time_hours and previous_sales are passed in by the caller
    (the backend) since the ML service doesn't hold store data itself.
    """
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
