import asyncio

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

app = FastAPI(title="MEV-Boost Analytics (Local)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = str(__file__).rsplit("/", 1)[0] + "/static"
app.mount("/static", StaticFiles(directory=static_dir, html=True), name="static")

@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/static/index.html", status_code=302)

RELAYS = [
    "https://titanrelay.xyz",
    "https://aestus.live",
    "https://agnostic-relay.net",
    "https://boost-relay.flashbots.net",
    "https://relay.ethgas.com",
    "https://relay.btcs.com",
]


def _parse_value_to_eth(value: "object") -> float:
    try:
        # Common formats: hex string in wei (e.g. "0x..."), or int wei, or decimal ether
        if isinstance(value, str):
            v = int(value, 16) if value.startswith("0x") else float(value)
        elif isinstance(value, (int, float)):
            v = value
        else:
            return 0.0
        # Heuristic: consider values > 1e12 as wei; convert to ETH
        if isinstance(v, float) and v < 1e6:
            return float(v)
        return float(v) / 1e18
    except Exception:
        return 0.0


async def fetch_relay_revenue_eth(client: httpx.AsyncClient, base_url: str, limit: int = 200) -> float:
    paths = [
        f"/relay/v1/data/bidtraces/proposer_payload_delivered?limit={limit}",
        f"/relay/v1/data/bidtraces/builder_blocks_received?limit={limit}",
    ]
    for path in paths:
        try:
            resp = await client.get(base_url.rstrip("/") + path, timeout=15)
            if resp.status_code != 200:
                continue
            try:
                data = resp.json()
            except Exception:
                continue
            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict) and isinstance(data.get("data"), list):
                items = data["data"]
            total_eth = 0.0
            for it in items:
                # common keys: value, block_value, builder_profit, etc.
                for key in ("value", "block_value", "builder_profit", "profit"):
                    if key in it:
                        total_eth += _parse_value_to_eth(it[key])
                        break
            if total_eth > 0:
                return total_eth
        except Exception:
            continue
    return 0.0


@app.get("/api/revenue")
async def revenue_overview(limit: int = 200) -> dict:
    async with httpx.AsyncClient() as client:
        totals = await asyncio.gather(*[fetch_relay_revenue_eth(client, r, limit=limit) for r in RELAYS])
        per = [{"relay": r, "eth": t, "usd": None} for r, t in zip(RELAYS, totals)]
        return {"items": per, "total_eth": sum(totals)}


