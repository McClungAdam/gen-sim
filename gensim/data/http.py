"""HTTP helpers shared by all fetchers (ported from Historical_gensim's http_get + pagination).

- http_get: retries with exponential backoff on network errors, 429 and 5xx; 4xx fails at once.
- Error messages never contain API keys (requests embeds the full URL in HTTPError text).
- eia_v2_data: pages through an EIA v2 /data route (max 5,000 rows per request).
"""
from __future__ import annotations

import time
from typing import Iterable

import requests

from gensim.config import eia_api_key, redact

EIA_V2 = "https://api.eia.gov/v2"
EIA_PAGE = 5000
RETRY_STATUS = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    """A request failed after retries. Message is redacted."""


def http_get(url: str, *, params=None, headers=None, retries: int = 4, backoff: float = 1.6,
             timeout: float = 60, sleep=time.sleep) -> requests.Response:
    last: str = ""
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            last = f"{type(e).__name__}: {redact(e)}"
        else:
            if r.status_code < 400:
                return r
            last = f"HTTP {r.status_code} from {redact(r.url)}: {redact(r.text[:300])}"
            if r.status_code not in RETRY_STATUS:
                raise FetchError(last)
        if attempt < retries - 1:
            sleep(backoff ** attempt)
    raise FetchError(f"failed after {retries} attempts: {last}")


def eia_v2_data(route: str, *, frequency: str, data: Iterable[str] = ("value",),
                facets: dict[str, Iterable[str]] | None = None, start: str | None = None,
                end: str | None = None, sort: tuple[str, str] = ("period", "asc"),
                session_get=http_get) -> list[dict]:
    """All rows of an EIA v2 data route, paginated. `route` like 'electricity/facility-fuel'."""
    params: list[tuple[str, str]] = [("api_key", eia_api_key()), ("frequency", frequency)]
    params += [(f"data[{i}]", d) for i, d in enumerate(data)]
    for facet, values in (facets or {}).items():
        params += [(f"facets[{facet}][]", str(v)) for v in values]
    if start:
        params.append(("start", start))
    if end:
        params.append(("end", end))
    params += [("sort[0][column]", sort[0]), ("sort[0][direction]", sort[1])]

    rows: list[dict] = []
    offset = 0
    while True:
        page = params + [("offset", str(offset)), ("length", str(EIA_PAGE))]
        payload = session_get(f"{EIA_V2}/{route.strip('/')}/data/", params=page).json()
        if "error" in payload:
            raise FetchError(f"EIA error for {route}: {redact(payload['error'])}")
        resp = payload.get("response", {})
        batch = resp.get("data", [])
        rows.extend(batch)
        total = int(resp.get("total", len(rows)) or 0)
        if not batch or len(batch) < EIA_PAGE or len(rows) >= total:
            return rows
        offset += EIA_PAGE
