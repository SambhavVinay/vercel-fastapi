from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def function():
    return {'message' : 'running'}