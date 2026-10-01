import re
import unicodedata
from datetime import datetime, timezone

from curl_cffi import requests

API = "https://api.wallapop.com/api/v3"
SORTS = {
    "relevance": "most_relevance",
    "new": "newest",
    "near": "closest",
    "cheap": "price_low_to_high",
    "dear": "price_high_to_low",
}
MAX_PAGES = 25


class WallapopError(Exception):
    pass


def _get(path, params=None):
    # The API wants this header and a browser TLS fingerprint; plain clients get blocked.
    r = requests.get(f"{API}{path}", params=params, headers={"X-DeviceOS": "0"}, impersonate="chrome", timeout=30)
    if r.status_code != 200:
        raise WallapopError(f"{path}: HTTP {r.status_code} {r.text[:200]}")
    return r.json()


def geocode(place):
    """Town name -> (lat, lon, label) via OpenStreetMap Nominatim."""
    r = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": place, "format": "json", "limit": 1, "countrycodes": "es,pt"},
        headers={"User-Agent": "wallapop-cli"},
        timeout=20,
    )
    hits = r.json() if r.status_code == 200 else []
    if not hits:
        raise WallapopError(f"couldn't find a place called {place!r}")
    h = hits[0]
    return float(h["lat"]), float(h["lon"]), h["display_name"].split(",")[0]


def _fold(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def _row(it):
    loc = it.get("location") or {}
    ship = it.get("shipping") or {}
    return {
        "id": it["id"],
        "title": it["title"],
        "price": it["price"]["amount"],
        "currency": it["price"]["currency"],
        "city": loc.get("city"),
        "country": loc.get("country_code"),
        "ships": bool(ship.get("item_is_shippable") and ship.get("user_allows_shipping")),
        "reserved": it.get("reserved", {}).get("flag", False),
        "created": datetime.fromtimestamp(it["created_at"] / 1000, timezone.utc).strftime("%Y-%m-%d"),
        "description": it.get("description") or "",
        "url": f"https://es.wallapop.com/item/{it['web_slug']}",
    }


def search(query, *, min_price=None, max_price=None, near=None, radius_km=None, sort=None,
           limit=40, strict=True, ships_only=False):
    params = {"keywords": query, "source": "search_box"}
    if min_price is not None:
        params["min_sale_price"] = min_price
    if max_price is not None:
        params["max_sale_price"] = max_price
    where = None
    if near:
        lat, lon, where = geocode(near)
        params.update(latitude=lat, longitude=lon)
        # Wallapop only honours distance when sorting by proximity.
        if radius_km:
            params["distance"] = int(radius_km * 1000)
            sort = sort or "near"
    if sort:
        params["order_by"] = SORTS[sort]

    words = [_fold(w) for w in re.findall(r"\w+", query)]
    out, seen, page = [], set(), 0
    d = _get("/search", params)
    while True:
        for it in d["data"]["section"]["payload"]["items"]:
            row = _row(it)
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            if strict and not all(w in _fold(row["title"]) for w in words):
                continue
            if ships_only and not row["ships"]:
                continue
            out.append(row)
        nxt = d.get("meta", {}).get("next_page")
        page += 1
        # Price sorts return short (sometimes empty) pages, so keep paging until the limit.
        if len(out) >= limit or not nxt or page >= MAX_PAGES:
            break
        d = _get("/search", {"next_page": nxt})
    return out[:limit], where


def item(ref):
    item_id = ref if re.fullmatch(r"[a-z0-9]{10,14}", ref) else None
    if item_id is None:
        # Web URLs end in a numeric legacy id; the page embeds the API id.
        url = ref if ref.startswith("http") else f"https://es.wallapop.com/item/{ref}"
        html = requests.get(url, impersonate="chrome", timeout=30).text
        m = re.search(r'"pageProps":\{"item":\{"id":"([a-z0-9]+)"', html)
        if not m:
            raise WallapopError(f"couldn't find an item id in {ref}")
        item_id = m.group(1)
    d = _get(f"/items/{item_id}")
    loc = d.get("location") or {}
    return {
        "id": d["id"],
        "title": d["title"]["original"],
        "description": d["description"]["original"],
        "price": d["price"]["cash"]["amount"],
        "city": loc.get("city"),
        "country": loc.get("country_code"),
        "ships": bool((d.get("shipping") or {}).get("user_allows_shipping")),
        "condition": (d.get("type_attributes") or {}).get("condition", {}).get("text"),
        "views": (d.get("counters") or {}).get("views"),
        "favorites": (d.get("counters") or {}).get("favorites"),
        "modified": datetime.fromtimestamp(d["modified_date"], timezone.utc).strftime("%Y-%m-%d"),
        "url": d.get("share_url"),
    }
