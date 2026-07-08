"""Shared slowapi rate limiter and per-route limit strings.

Limits are per-client-IP. Override via env:
* ``OFV_RATE_LIMIT_FAIRVALUE`` — /fairvalue (CPU-heavy Monte Carlo), default 10/minute
* ``OFV_RATE_LIMIT_DATA`` — /chain and /expiries (proxy yfinance), default 30/minute
"""
from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

RATE_LIMIT_FAIRVALUE = os.environ.get("OFV_RATE_LIMIT_FAIRVALUE", "10/minute")
RATE_LIMIT_DATA = os.environ.get("OFV_RATE_LIMIT_DATA", "30/minute")
