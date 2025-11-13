from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

# 내부 import
from app.api.routes import router as api_router
from app.config import settings
from core.logger import *



app = FastAPI(
    title="LLeX.Ai FastAPI Backend",
    description="GPT-4o 기반 Adaptive Streaming 챗봇 백엔드",
    version="0.8.2",
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:5173", "http://localhost:5174", "http://localhost:5177",
        "http://127.0.0.1:5173", "http://127.0.0.1:5174", "http://127.0.0.1:5177"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>L.Ai Backend</title>
    </head>
    <body>
        <h1>L.Ai FastAPI Backend is running!</h1>
        <p>Visit <a href="/docs">/docs</a> for API documentation.</p>
    </body>
    </html>
    """

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": app.version}
