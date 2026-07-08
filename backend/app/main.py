from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # load backend/.env if present

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.analysis import Scanner
from app.api import alerts as alerts_router
from app.api import analysis as analysis_router
from app.api import chain as chain_router
from app.api import expiries as expiries_router
from app.api import fairvalue as fairvalue_router
from app.api.limits import limiter
from app.data.cache import Cache
from app.data.fred_client import FredClient
from app.data.yfinance_client import YFinanceClient

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
DEFAULT_STATIC_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = Cache()
    app.state.cache = cache
    app.state.yfinance = YFinanceClient(cache=cache)
    fred = None
    fred_key = os.environ.get("FRED_API_KEY")
    if fred_key:
        try:
            fred = FredClient(api_key=fred_key, cache=cache)
            logger.info("FRED client initialised")
        except Exception as exc:
            logger.warning("FRED client init failed: %s", exc)
    else:
        logger.warning("FRED_API_KEY not set; /fairvalue will 503 unless risk_free_rate is overridden")
    app.state.fred = fred

    scanner = None
    # Off by default: a background process hitting Yahoo on a timer should be
    # an explicit choice, not a surprise side effect of starting the API.
    if os.environ.get("OFV_SCANNER_ENABLED", "0") == "1":
        scanner = Scanner(yfinance=app.state.yfinance, cache=cache, fred=fred)
        scanner.start()
    else:
        logger.info("Mispricing scanner disabled (set OFV_SCANNER_ENABLED=1 to enable)")
    app.state.scanner = scanner

    yield
    if scanner is not None:
        await scanner.stop()
    cache.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Option Fair Value Dashboard API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # When the frontend is served by this app (see static mount below) the UI is
    # same-origin and CORS never applies; the list only matters for split deploys
    # and local dev. Comma-separated origins, e.g. "https://app.example.com".
    origins = [
        o.strip()
        for o in os.environ.get("OFV_CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(expiries_router.router)
    app.include_router(chain_router.router)
    app.include_router(fairvalue_router.router)
    app.include_router(analysis_router.router)
    app.include_router(alerts_router.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {
            "status": "ok",
            "fred_enabled": getattr(app.state, "fred", None) is not None,
            "scanner_enabled": getattr(app.state, "scanner", None) is not None,
        }

    # Serve the built frontend (if present) from the same origin. Mounted last so
    # API routes take precedence. html=True serves index.html at "/".
    static_dir = Path(os.environ.get("OFV_STATIC_DIR", DEFAULT_STATIC_DIR))
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
        logger.info("Serving frontend from %s", static_dir)
    else:
        logger.info("No frontend build at %s; API-only mode", static_dir)

    return app


app = create_app()
