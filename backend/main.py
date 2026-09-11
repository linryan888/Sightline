from fastapi import FastAPI, status
from pydantic import BaseModel

# 1. Initialize the FastAPI app
app = FastAPI()

# 2. Define a Pydantic model for data validation (for POST/PUT requests)
class Item(BaseModel):
    name: str
    price: float
    description: str | None = None

# 3. Create a simple GET endpoint (Root)
@app.get("/")
def read_root():
    return {"message": "Welcome to your FastAPI backend!"}

# 4. Create a GET endpoint with a path parameter
@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "query_parameter": q}

# 5. Create a POST endpoint that accepts JSON data matching the Item model
@app.post("/items/", status_code=status.HTTP_201_CREATED)
def create_item(item: Item):
    return {"message": "Item created successfully", "data": item}