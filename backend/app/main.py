from fastapi import FastAPI

app = FastAPI(title="Fault Localization System")


@app.get("/")
def root():
    return {"message": "Fault Localization API is running"}