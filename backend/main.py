from fastapi import FastAPI

app = FastAPI(title="Helix-Signal API")


@app.get("/")
def root() -> str:
    return "Hello Helix-Signal!"


@app.get("/api/dashboard")
def dashboard() -> dict:
    return {
        "status": "placeholder",
        "message": "Dashboard endpoint is under construction.",
    }
