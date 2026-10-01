"""Logged-in features: inbox, messages, offers.

Wallapop's web app holds a 30-day HttpOnly NextAuth cookie and swaps it at
/api/auth/session for a five-minute bearer token. Chat runs over PubNub on
channels Wallapop hands out; the CLI never builds a channel name itself.
"""

import base64
import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from curl_cffi import requests

from .client import WallapopError, item

WEB = "https://es.wallapop.com"
API = "https://api.wallapop.com"
PUBNUB = "https://ps.pndsn.com"
PUB_KEY = "pub-c-255dc549-86f5-4abd-8b9e-921d5a02fde7"
SUB_KEY = "sub-c-89405e27-d4df-4d87-aca1-d6e9118f0a0d"
COOKIE = "__Secure-next-auth.session-token"
STORE = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "wallapop" / "session.json"


def _save(data):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.touch(mode=0o600, exist_ok=True)
    STORE.write_text(json.dumps(data))
    STORE.chmod(0o600)


def cookie_from_chrome():
    """Read the session cookie out of Chrome's cookie store (macOS asks for Keychain access once)."""
    try:
        from pycookiecheat import BrowserType, get_cookies
    except ImportError:
        raise WallapopError("reading Chrome cookies needs pycookiecheat: uv tool install --with pycookiecheat ...")
    jar = get_cookies(WEB, browser=BrowserType.CHROME)
    if not jar.get(COOKIE):
        raise WallapopError("Chrome has no Wallapop session. Log in at es.wallapop.com in Chrome first")
    return jar[COOKIE]


def login(cookie):
    s = Session(cookie)
    s.token()
    me = s.get("/api/v3/users/me")
    return me.get("micro_name") or me.get("id")


class Session:
    def __init__(self, cookie=None):
        if cookie is None:
            if not STORE.exists():
                raise WallapopError("not logged in. Run: wallapop login")
            cookie = json.loads(STORE.read_text())["cookie"]
        self.cookie = cookie
        self._token, self._exp = None, 0
        self._pn_token, self._pn_exp = None, 0
        self._me = None

    def token(self):
        if self._token and self._exp - time.time() > 30:
            return self._token
        r = requests.get(f"{WEB}/api/auth/session", headers={"Cookie": f"{COOKIE}={self.cookie}"},
                         impersonate="chrome", timeout=30)
        tok = (r.json() if r.status_code == 200 else {}).get("token")
        if not tok:
            raise WallapopError("the Wallapop session has expired. Log in again in Chrome, then run: wallapop login")
        # Each mint rotates the cookie and slides its 30-day expiry; keep the newest.
        fresh = r.cookies.get(COOKIE)
        if fresh:
            self.cookie = fresh
        _save({"cookie": self.cookie})
        payload = json.loads(base64.urlsafe_b64decode(tok.split(".")[1] + "=="))
        self._token, self._exp = tok, payload.get("exp", time.time() + 240)
        return tok

    def _req(self, method, path, params=None, body=None, extra=None):
        headers = {"Authorization": f"Bearer {self.token()}", "X-DeviceOS": "0", "Accept": "application/json", **(extra or {})}
        r = requests.request(method, f"{API}{path}", params=params, json=body, headers=headers,
                             impersonate="chrome", timeout=30)
        if r.status_code >= 400:
            raise WallapopError(f"{method} {path}: HTTP {r.status_code} {r.text[:300]}")
        return r.json() if r.text.strip() else None

    def get(self, path, params=None, extra=None):
        return self._req("GET", path, params, extra=extra)

    def post(self, path, body, extra=None):
        return self._req("POST", path, body=body, extra=extra)

    # Inbox and conversations

    def inbox(self, limit=20):
        d = self.get("/bff/messaging/inbox", {"page_size": limit, "max_messages": 1})
        self._me = d.get("user_hash")
        return d.get("conversations", [])

    def me(self):
        if not self._me:
            self.inbox(1)
        return self._me

    def conversation(self, conv_hash):
        return self.get(f"/bff/messaging/conversation/{conv_hash}")

    def conversation_for(self, ref):
        """A conversation hash, or an item id/URL: reuse the existing thread about that item."""
        convs = self.inbox(100)
        for c in convs:
            if c["hash"] == ref:
                return self.conversation(ref)
        item_id = item(ref)["id"]
        for c in convs:
            if (c.get("item") or {}).get("hash") == item_id:
                return self.conversation(c["hash"])
        return None

    def start(self, item_id):
        try:
            new = self.post("/api/v3/instant-messaging/conversation", {"item_hash_id": item_id})
        except WallapopError as e:
            if '"code":100' in str(e).replace(" ", ""):
                raise WallapopError("Wallapop won't let this account open more new conversations right now")
            raise
        return self.conversation(new["conversation_id"])

    # PubNub

    def _pn(self):
        # The PAM token lives 60 minutes; refresh well before that.
        if not self._pn_token or time.time() > self._pn_exp:
            self._pn_token = self.get("/api/v3/instant-messaging/token")["token"]
            self._pn_exp = time.time() + 600
        return {"uuid": self.me(), "auth": self._pn_token, "pnsdk": "wallapop-cli"}

    def send(self, conv, text):
        if not conv.get("channel"):
            raise WallapopError("conversation has no channel to publish on")
        msg = {"id": str(uuid.uuid4()), "payload": {"text": text}}
        meta = {
            "type": "text",
            "sender": {"platform": {"app_version": "web", "os_version": "0"}},
            "to_user_hash": conv["with_user"]["hash"],
            "from_user_hash": self.me(),
            "conversation_hash": conv["hash"],
        }
        params = {**self._pn(), "meta": json.dumps(meta, separators=(",", ":"))}
        path = f"/publish/{PUB_KEY}/{SUB_KEY}/0/{quote(conv['channel'], safe='')}/0/{quote(json.dumps(msg, separators=(',', ':')), safe='')}"
        r = requests.get(f"{PUBNUB}{path}", params=params, impersonate="chrome", timeout=30)
        out = r.json() if r.status_code == 200 else None
        if not out or out[0] != 1:
            raise WallapopError(f"PubNub rejected the message: HTTP {r.status_code} {r.text[:200]}")
        return msg["id"]

    # Offers (Wallapop's own make-an-offer, not a chat message)

    def offer_terms(self, item_id):
        d = self.get("/bff/delivery/make-an-offer", {"item_id": item_id}, extra={"X-AppVersion": "0"})
        r = d.get("restriction") or {}
        price = (d.get("items_price") or {})
        if r.get("max_offer_percentage") is None or not price.get("amount"):
            raise WallapopError("offer terms came back incomplete; nothing was sent")
        return {
            "price": price["amount"],
            "currency": price["currency"],
            "min": round(price["amount"] * (100 - r["max_offer_percentage"])) / 100,
            "remaining": r.get("remaining_offers_per_day"),
            "per_day": r.get("max_offers_per_day"),
        }

    def offer(self, item_id, amount, currency):
        self.post("/api/v3/delivery/buyer/offers", {
            "offer_id": str(uuid.uuid4()),
            "offer_price_amount": amount,
            "offer_price_currency": currency,
            "item_ids": [item_id],
        }, extra={"X-AppVersion": "0"})
