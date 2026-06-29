from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import jobs, music

app = FastAPI(
    title="ClipFlow Pipeline API",
    description="Backend for the ClipFlow automated podcast-clipping pipeline.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
app.include_router(music.router, prefix="/music", tags=["Music"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ClipFlow Pipeline API"}
