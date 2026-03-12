import uvicorn
from fastapi import FastAPI
from typing import Union

fastapi_app = FastAPI()



@fastapi_app.get("/")
def read_root():
    return {"message": "Hello, World!"}


if __name__ == "__main__":
    uvicorn.run(fastapi_app, host="0.0.0.0", port=5000)
