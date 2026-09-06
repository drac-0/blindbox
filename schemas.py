from pydantic import BaseModel
from datetime import datetime

class UserCreate(BaseModel):
    username: str
    email: str
    role: str = "customer"

class UserResponse(UserCreate):
    user_id: int
    created_at: datetime

class StoreResponse(BaseModel):
    store_id: int
    store_name: str
    address: str
    jarak: float

class OrderCreate(BaseModel):
    user_id: int
    store_id: int
    harga: float

class OrderResponse(OrderCreate):
    order_id: int
    status: str
    created_at: datetime
