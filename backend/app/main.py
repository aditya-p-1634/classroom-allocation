"""Main FastAPI Application Entrypoint for ClassroomIQ REST Bridge."""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api import status, inventory, allocation, validation, simulation, upload

app = FastAPI(
    title="ClassroomIQ — Smart Classroom Allocation REST API",
    description="REST API Bridge and Static Host for ClassroomIQ Frontend Integration (Phase P7).",
    version="0.2.6",
)

# CORS middleware for local frontend development and testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(status.router, prefix="/api")
app.include_router(inventory.router, prefix="/api")
app.include_router(allocation.router, prefix="/api")
app.include_router(validation.router, prefix="/api")
app.include_router(simulation.router, prefix="/api")
app.include_router(upload.router, prefix="/api")


@app.get("/api/health")
def health_check():
    """Lightweight health check endpoint."""
    return {"status": "ok", "app": "ClassroomIQ", "version": "0.2.5"}


# Mount static frontend assets if frontend directory exists
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")
