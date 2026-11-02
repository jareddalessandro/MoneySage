"""Per-visitor request limits, so one client can't hammer sign-in, invites, uploads or the API in general.

In memory, which fits the single backend process this app runs (the scheduler lives in it too, so it's
never run with several workers). Behind Caddy, uvicorn's --proxy-headers makes request.client the real
visitor. Limits reset when the backend restarts, which is fine for this purpose.
"""

import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import settings

WRITES = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True)
class Rule:
    name: str
    limit: int
    window: int  # seconds
    matches: Callable[[str, str], bool]  # (method, path under /api/)


def _invite(method: str, path: str) -> bool:
    return method == "POST" and (
        path == "/api/household/access/invites"
        or (path.startswith("/api/companies/") and path.endswith("/access/invites"))
    )


# A request counts against every rule it matches.
RULES: tuple[Rule, ...] = (
    Rule("sign-in", 20, 60, lambda m, p: p.startswith("/api/auth/")),
    Rule("invites", 30, 3600, _invite),
    Rule("uploads", 30, 3600, lambda m, p: m == "POST" and p in ("/api/import", "/api/statements/preview")),
    Rule("writes", 300, 60, lambda m, p: m in WRITES),
    Rule("all", 600, 60, lambda m, p: True),
)


class Limiter:
    def __init__(self, rules: tuple[Rule, ...] = RULES):
        self.rules = rules
        self.hits: dict[tuple[str, str], deque[float]] = {}
        self.last_sweep = time.monotonic()

    def check(self, client: str, method: str, path: str, now: float | None = None) -> int | None:
        """None if allowed (and counted); otherwise seconds until the client may try again."""
        now = time.monotonic() if now is None else now
        self._sweep(now)
        matched = [r for r in self.rules if r.matches(method, path)]
        for rule in matched:
            hits = self.hits.get((rule.name, client))
            if hits is not None:
                while hits and hits[0] <= now - rule.window:
                    hits.popleft()
                if len(hits) >= rule.limit:
                    return max(1, math.ceil(hits[0] + rule.window - now))
        for rule in matched:
            self.hits.setdefault((rule.name, client), deque()).append(now)
        return None

    def _sweep(self, now: float) -> None:
        # Forget idle clients now and then so memory doesn't grow with every visitor ever seen.
        if now - self.last_sweep < 300:
            return
        self.last_sweep = now
        longest = max(r.window for r in self.rules)
        for key in [k for k, hits in self.hits.items() if not hits or hits[-1] <= now - longest]:
            del self.hits[key]


limiter = Limiter()


async def rate_limit(request: Request, call_next):
    if settings.rate_limit_enabled and request.url.path.startswith("/api/"):
        client = request.client.host if request.client else "unknown"
        retry = limiter.check(client, request.method, request.url.path)
        if retry is not None:
            return JSONResponse(
                {"detail": "Too many requests. Wait a moment and try again."},
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
    return await call_next(request)
