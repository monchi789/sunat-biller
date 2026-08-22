import uvicorn
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}


# This function is used to start the development server
def dev():
    """
    Starts the development server using Uvicorn.
    """
    return uvicorn.run("app.main:app", host="0.0.0.0", port=7890, reload=True)


def prod():
    """
    Starts the production server using Uvicorn.
    """
    return uvicorn.run("app.main:app", host="0.0.0.0", port=7890, reload=False)
