"""FastAPI entry point. Also serves the built frontend when it exists."""
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from config import ALLOWED_ORIGINS, BACKGROUND, BASE_DIR, CURRENCIES, RATE_LIMIT, TIMEFRAMES, UNIVERSE
from routes.analyze import router as analyze_router, snapshot
from routes.model import router as model_router
from services.ml_scorer import bundle



def _keep_fresh():
    """Keep caches warm and the live track record growing even when nobody is visiting."""
    while True:
        for tf in TIMEFRAMES:
            try:
                if bundle(tf):
                    snapshot(tf)
            except Exception as e:
                print(f"[background] {tf}: {e}")
        time.sleep(300)


@asynccontextmanager
async def lifespan(_):
    if BACKGROUND:
        threading.Thread(target=_keep_fresh, daemon=True).start()
    yield


app = FastAPI(title="ITDSS", description="Intelligent Trading Decision Support System. Educational use only.",
              version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://itdss-frontend.onrender.com"
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"]
)

# ponytail: per-process sliding window; use a shared store (Redis) if you run several workers.
_hits: dict = defaultdict(deque)


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        now, ip = time.monotonic(), request.client.host if request.client else "?"
        if len(_hits) > 10_000:
            for k in [k for k, v in _hits.items() if not v or v[-1] < now - 60]:
                del _hits[k]
        q = _hits[ip]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return JSONResponse({"detail": "too many requests"}, 429, {"Retry-After": "30"})
        q.append(now)
    res = await call_next(request)
    res.headers["X-Content-Type-Options"] = "nosniff"
    res.headers["Referrer-Policy"] = "no-referrer"
    res.headers["X-Frame-Options"] = "DENY"
    return res


app.include_router(analyze_router, prefix="/api")
app.include_router(model_router, prefix="/api")


@app.get("/api/health", tags=["Health"])
def health():
    return {"status": "ok", "models": {tf: bundle(tf) is not None for tf in TIMEFRAMES}}


@app.get("/api/symbols", tags=["Symbols"])
def symbols():
    return {"universe": UNIVERSE, "timeframes": list(TIMEFRAMES), "currencies": CURRENCIES}


DIST = BASE_DIR.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="app")
