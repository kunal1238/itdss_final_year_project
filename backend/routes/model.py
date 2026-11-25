"""Model card and guarded retraining."""
import hmac
import threading
import traceback
from typing import Literal

from fastapi import APIRouter, Header, HTTPException

from config import ADMIN_TOKEN
from services.ml_scorer import report
from services.training import train

router = APIRouter(tags=["Model"])
_job = {"running": False, "log": [], "error": None}
_lock = threading.Lock()


@router.get("/model")
def model(timeframe: Literal["1h", "1d"] = "1h"):
    r = report(timeframe)
    if r is None:
        raise HTTPException(404, "model not trained yet")
    return r


def _run(tf):
    try:
        train(tf, lambda m: _job["log"].append(m))
    except Exception as e:
        traceback.print_exc()
        _job["error"] = type(e).__name__
    finally:
        _job["running"] = False


@router.post("/train", status_code=202)
def start(timeframe: Literal["1h", "1d"] = "1h", x_admin_token: str = Header("")):
    if not ADMIN_TOKEN or not hmac.compare_digest(x_admin_token.encode(), ADMIN_TOKEN.encode()):
        raise HTTPException(403, "retraining requires the admin token")
    with _lock:
        if _job["running"]:
            raise HTTPException(409, "training is already running")
        _job.update(running=True, log=[], error=None)
    threading.Thread(target=_run, args=(timeframe,), daemon=True).start()
    return {"status": "started"}


@router.get("/train")
def status():
    return {"enabled": bool(ADMIN_TOKEN), **_job, "log": _job["log"][-20:]}
