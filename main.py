from fastapi import FastAPI
from datetime import datetime
from typing import List
from schemas import UserCreate, UserResponse, StoreResponse, OrderCreate, OrderResponse

app = FastAPI(
    title="BlindBox Eco API",
    description="API Backend untuk aplikasi BlindBox Eco"
)

# Dummy Data sementara
fake_users = []
fake_stores = [
    {"store_id": 1, "store_name": "Toko Roti Bundar", "address": "Jl. Mawar No. 12", "jarak": 1.2},
    {"store_id": 2, "store_name": "Kopi Kawa", "address": "Jl. Melati No. 5", "jarak": 0.8}
]
fake_orders = []

@app.get("/", tags=["Root"])
def home():
    return {"message": "API BlindBox Eco Berhasil Jalan!"}

# Endpoint Register User
@app.post("/users/register", response_model=UserResponse, tags=["Users"])
def register_user(user: UserCreate):
    new_user = {**user.model_dump(), "user_id": len(fake_users) + 1, "created_at": datetime.now()}
    fake_users.append(new_user)
    return new_user

# Endpoint Get Stores (EcoMap)
@app.get("/stores", response_model=List[StoreResponse], tags=["Stores"])
def get_stores():
    return fake_stores

# Endpoint Create Order (QuickClaim)
@app.post("/orders", response_model=OrderResponse, tags=["Orders"])
def create_order(order: OrderCreate):
    new_order = {**order.model_dump(), "order_id": len(fake_orders) + 1, "status": "pending", "created_at": datetime.now()}
    fake_orders.append(new_order)
    return new_order