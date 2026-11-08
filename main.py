from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Import routes
from routes import auth, users, leaderboard
from utils.turso_storage import turso_storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    await turso_storage.initialize()
    yield

# Create FastAPI app
app = FastAPI(
    title="Noor API",
    description="""
    🌙 Noor - Islamic Companion App Backend

    ## Features

    - **Authentication**: Email and password accounts
    - **User Profiles**: Track progress and stats
    - **Leaderboard**: Global and country rankings
    - **Activity Logging**: Earn points for Islamic activities

    ## Points System

    - Quran reading: 10 points per surah each day
    - Daily prayers: 5 points per prayer each day
    - Lessons completed: 20 points per lesson
    - Dua memorized: 15 points per dua
    - Completed game levels: 10 points per level
    - Daily tasks: server-assigned rewards shown in the app

    Rewards are assigned by the server and duplicate activity submissions do
    not grant points more than once for the same activity period.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your Flutter app domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(leaderboard.router)

@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "message": "Noor API - Islamic Companion App",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "operational"
    }

@app.api_route("/health", methods=["GET", "HEAD"])
@app.api_route("/healthz", methods=["GET", "HEAD"])
async def health_check():
    """Liveness endpoint for uptime monitors."""
    return {
        "status": "healthy",
        "database": "turso",
    }

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"detail": "Endpoint not found"}
    )

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # All network interfaces for WiFi access
        port=port,
        reload=os.getenv("DEBUG", "False") == "True"
    )
