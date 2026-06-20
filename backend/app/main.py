from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # load backend/.env if present

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chain as chain_router
from app.api import expiries as expiries_router
from app.api import fairvalue as fairvalue_router
from app.data.cache import Cache
from app.data.fred_client import FredClient
from app.data.yfinance_client import YFinanceClient

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
    yield
    cache.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Option Fair Value Dashboard API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(expiries_router.router)
    app.include_router(chain_router.router)
    app.include_router(fairvalue_router.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {
            "status": "ok",
            "fred_enabled": getattr(app.state, "fred", None) is not None,
        }

    return app


app = create_app()
