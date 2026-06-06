from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# get_remote_address extracts the client IP from the request
# This is what we rate limit against — one limit per IP address
limiter = Limiter(key_func=get_remote_address)