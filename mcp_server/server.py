from pathlib import Path

import yaml

from common import config
from common.telemetry import instrument_app, setup_telemetry

CFG = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text(encoding="utf-8"))

setup_telemetry("mcp_server")  # must run before the MCP server is created

from datetime import date

from mcp.server.mcpserver import MCPServer
from opentelemetry import metrics
from starlette.requests import Request
from starlette.responses import JSONResponse

mcp = MCPServer(CFG["name"], version=CFG["version"], instructions=CFG["instructions"].strip())

TOOL_CALLS = metrics.get_meter("mcp_server").create_counter(
    "mcp_tool_calls", description="Number of MCP tool calls, by tool"
)

WEEKEND_PREMIUM = 1.25  # Friday and Saturday pricing

# ---- Mock data. In production this would be a database or vendor API. ----
VENUES = [
    {"id": "V001", "name": "Rooftop Social", "city": "New York", "type": "rooftop",
     "capacity": 80, "base_price_per_hour": 400, "min_hours": 4, "cleaning_fee": 250,
     "deposit_pct": 0.30, "alcohol_allowed": True, "indoor": False, "curfew": "23:00",
     "accessible": True, "in_house_catering_required": False,
     "cancellation_policy": "Full refund 30+ days out, 50% at 14-29 days, none under 14 days.",
     "booked_dates": ["2026-11-14", "2026-11-21"]},
    {"id": "V002", "name": "The Loft Hall", "city": "New York", "type": "banquet hall",
     "capacity": 150, "base_price_per_hour": 650, "min_hours": 5, "cleaning_fee": 400,
     "deposit_pct": 0.50, "alcohol_allowed": True, "indoor": True, "curfew": "01:00",
     "accessible": True, "in_house_catering_required": False,
     "cancellation_policy": "50% deposit non-refundable. Balance due 14 days before event.",
     "booked_dates": ["2026-12-12"]},
    {"id": "V003", "name": "Brooklyn Backyard Garden", "city": "New York", "type": "garden",
     "capacity": 50, "base_price_per_hour": 200, "min_hours": 3, "cleaning_fee": 150,
     "deposit_pct": 0.25, "alcohol_allowed": False, "indoor": False, "curfew": "22:00",
     "accessible": False, "in_house_catering_required": False,
     "cancellation_policy": "Full refund up to 7 days before the event.",
     "booked_dates": []},
    {"id": "V004", "name": "Lone Star Barn", "city": "Austin", "type": "barn",
     "capacity": 120, "base_price_per_hour": 350, "min_hours": 4, "cleaning_fee": 300,
     "deposit_pct": 0.30, "alcohol_allowed": True, "indoor": True, "curfew": "00:00",
     "accessible": True, "in_house_catering_required": False,
     "cancellation_policy": "Full refund 21+ days out, none after.",
     "booked_dates": ["2026-11-28"]},
    {"id": "V005", "name": "Congress Ave Lounge", "city": "Austin", "type": "lounge",
     "capacity": 60, "base_price_per_hour": 300, "min_hours": 3, "cleaning_fee": 200,
     "deposit_pct": 0.25, "alcohol_allowed": True, "indoor": True, "curfew": "02:00",
     "accessible": True, "in_house_catering_required": True,
     "cancellation_policy": "Full refund 14+ days out.",
     "booked_dates": []},
    {"id": "V006", "name": "Lakeview Pavilion", "city": "Chicago", "type": "pavilion",
     "capacity": 100, "base_price_per_hour": 275, "min_hours": 4, "cleaning_fee": 200,
     "deposit_pct": 0.30, "alcohol_allowed": True, "indoor": False, "curfew": "22:30",
     "accessible": True, "in_house_catering_required": False,
     "cancellation_policy": "Full refund 30+ days out, 25% fee after.",
     "booked_dates": []},
    {"id": "V007", "name": "Windy City Arcade Bar", "city": "Chicago", "type": "arcade bar",
     "capacity": 70, "base_price_per_hour": 450, "min_hours": 3, "cleaning_fee": 300,
     "deposit_pct": 0.40, "alcohol_allowed": True, "indoor": True, "curfew": "01:00",
     "accessible": True, "in_house_catering_required": False,
     "cancellation_policy": "Deposit non-refundable. Reschedule once for free.",
     "booked_dates": ["2026-12-05"]},
]

CATERERS = [
    {"id": "C01", "vendor": "Slice Brothers", "style": "pizza", "per_person": 14,
     "min_guests": 10, "dietary_support": ["vegetarian", "vegan"], "lead_time_days": 3},
    {"id": "C02", "vendor": "Tapas & Co", "style": "finger_food", "per_person": 26,
     "min_guests": 20, "dietary_support": ["vegetarian", "gluten-free"], "lead_time_days": 7},
    {"id": "C03", "vendor": "Harvest Table", "style": "buffet", "per_person": 38,
     "min_guests": 30, "dietary_support": ["vegetarian", "vegan", "gluten-free", "halal"],
     "lead_time_days": 10},
    {"id": "C04", "vendor": "Maison Plated", "style": "plated", "per_person": 72,
     "min_guests": 25, "dietary_support": ["vegetarian", "vegan", "gluten-free", "halal", "kosher"],
     "lead_time_days": 14},
]

ENTERTAINERS = [
    {"id": "E01", "name": "DJ Nova", "category": "DJ", "fee": 600,
     "party_types": ["birthday", "wedding", "graduation"], "age_groups": ["teens", "adults"],
     "booked_dates": ["2026-12-12"]},
    {"id": "E02", "name": "Bounce Party Co", "category": "inflatables", "fee": 350,
     "party_types": ["birthday"], "age_groups": ["kids"], "booked_dates": []},
    {"id": "E03", "name": "Jazz Trio", "category": "live band", "fee": 900,
     "party_types": ["wedding", "birthday"], "age_groups": ["adults"], "booked_dates": []},
    {"id": "E04", "name": "Photo Booth Pro", "category": "photo booth", "fee": 300,
     "party_types": ["birthday", "wedding", "graduation"],
     "age_groups": ["kids", "teens", "adults"], "booked_dates": []},
    {"id": "E05", "name": "Magic & Balloons", "category": "magician", "fee": 280,
     "party_types": ["birthday"], "age_groups": ["kids"], "booked_dates": []},
]


def _parse_date(event_date: str):
    try:
        return date.fromisoformat(event_date)
    except ValueError:
        return None


@mcp.tool()
def search_venues(
    city: str,
    guest_count: int,
    event_date: str,
    max_price_per_hour: float = 0,
    venue_type: str = "",
    alcohol_required: bool = False,
) -> list[dict]:
    """Find venues in a city that are AVAILABLE on event_date (YYYY-MM-DD) and fit
    the guest count. Prices already include the Friday/Saturday premium. Set
    max_price_per_hour to 0 for no limit. Use alcohol_required=true to only get
    venues that allow alcohol."""
    TOOL_CALLS.add(1, {"tool": "search_venues"})
    d = _parse_date(event_date)
    if d is None:
        return [{"error": "event_date must be in YYYY-MM-DD format."}]
    weekend = d.weekday() in (4, 5)
    results = []
    for v in VENUES:
        if v["city"].lower() != city.lower():
            continue
        if v["capacity"] < guest_count or event_date in v["booked_dates"]:
            continue
        if alcohol_required and not v["alcohol_allowed"]:
            continue
        if venue_type and venue_type.lower() not in v["type"].lower():
            continue
        price = round(v["base_price_per_hour"] * (WEEKEND_PREMIUM if weekend else 1.0), 2)
        if max_price_per_hour and price > max_price_per_hour:
            continue
        results.append({
            "id": v["id"], "name": v["name"], "type": v["type"], "capacity": v["capacity"],
            "price_per_hour": price, "weekend_pricing_applied": weekend,
            "min_hours": v["min_hours"], "cleaning_fee": v["cleaning_fee"],
            "deposit_pct": v["deposit_pct"], "alcohol_allowed": v["alcohol_allowed"],
            "indoor": v["indoor"], "curfew": v["curfew"],
            "in_house_catering_required": v["in_house_catering_required"],
        })
    return results or [{"message": "No available venues matched. Try another date, city, or budget."}]


@mcp.tool()
def get_venue_details(venue_id: str) -> dict:
    """Get the full record for one venue, including cancellation policy,
    accessibility, curfew, and catering restrictions."""
    TOOL_CALLS.add(1, {"tool": "get_venue_details"})
    for v in VENUES:
        if v["id"].lower() == venue_id.lower():
            return {k: val for k, val in v.items() if k != "booked_dates"}
    return {"error": f"Unknown venue_id {venue_id}"}


@mcp.tool()
def get_catering_options(guest_count: int, dietary_needs: str = "") -> list[dict]:
    """List catering packages that accept this guest count and support ALL the
    given dietary needs (comma separated, e.g. 'vegetarian, halal'). Leave
    dietary_needs empty if there are none."""
    TOOL_CALLS.add(1, {"tool": "get_catering_options"})
    needs = [n.strip().lower() for n in dietary_needs.split(",") if n.strip()]
    results = []
    for c in CATERERS:
        if guest_count < c["min_guests"]:
            continue
        if not all(n in c["dietary_support"] for n in needs):
            continue
        results.append({**c, "estimated_total": c["per_person"] * guest_count})
    return results or [{"message": "No caterer matches those guest and dietary needs."}]


@mcp.tool()
def search_entertainment(
    party_type: str,
    age_group: str,
    event_date: str,
    max_fee: float = 0,
) -> list[dict]:
    """Find entertainers available on event_date (YYYY-MM-DD) for the party type
    (birthday, wedding, graduation) and age group (kids, teens, adults).
    Set max_fee to 0 for no limit."""
    TOOL_CALLS.add(1, {"tool": "search_entertainment"})
    results = []
    for e in ENTERTAINERS:
        if party_type.lower() not in e["party_types"]:
            continue
        if age_group.lower() not in e["age_groups"]:
            continue
        if event_date in e["booked_dates"]:
            continue
        if max_fee and e["fee"] > max_fee:
            continue
        results.append({"id": e["id"], "name": e["name"], "category": e["category"], "fee": e["fee"]})
    return results or [{"message": "No entertainers available for those criteria."}]


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "mcp_server"})


# Streamable HTTP endpoint: http://<host>:8002/mcp
app = mcp.streamable_http_app(host=config.BIND_HOST)

# No HTTP spans for /mcp: the MCP client posts from a background task without a
# traceparent header, so those spans would land in orphan traces. MCP carries
# trace context in each message's _meta instead, and the SDK's built-in
# "tools/call <name>" spans join the caller's trace from there.
instrument_app(app, excluded_urls="health,mcp")