import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def _get_rate_limit_key() -> str:
    return get_remote_address()


limiter = Limiter(
    key_func=_get_rate_limit_key,
    default_limits=["200 per minute", "3000 per day"],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
)