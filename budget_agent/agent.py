from pathlib import Path

from common import config
from common.telemetry import instrument_app, setup_telemetry

setup_telemetry("budget_agent")  # before ADK is imported

import yaml
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import Agent
from opentelemetry import metrics

from common.health import health_route

CFG = yaml.safe_load((Path(__file__).parent / "instructions.yaml").read_text(encoding="utf-8"))

EVALUATIONS = metrics.get_meter("budget_agent").create_counter(
    "budget_evaluations", description="Options priced by the budget agent, by city and fit"
)

# Finance-team policy (mock)
TAX_RATES = {"new york": 0.08875, "austin": 0.0825, "chicago": 0.1025}
CATERING_SERVICE_CHARGE = 0.20
CONTINGENCY = 0.10


def calculate_event_cost(
    city: str,
    total_budget: float,
    venue_price_per_hour: float,
    hours: float,
    venue_fees: float,
    venue_deposit_pct: float,
    catering_per_person: float,
    guest_count: int,
    entertainment_cost: float,
) -> dict:
    """Fully loaded cost of ONE option (venue + catering + entertainment): includes
    sales tax, a 20% catering service charge, venue fees, and a 10% contingency.
    Returns the grand total, deposit due, and whether it fits the total budget."""
    rate = TAX_RATES.get(city.lower(), 0.08)
    venue_rental = venue_price_per_hour * hours
    venue_total = venue_rental + venue_fees
    catering = catering_per_person * guest_count
    service_charge = catering * CATERING_SERVICE_CHARGE
    pre_tax = venue_total + catering + service_charge + entertainment_cost
    tax = pre_tax * rate
    subtotal = pre_tax + tax
    contingency = subtotal * CONTINGENCY
    grand_total = subtotal + contingency
    EVALUATIONS.add(1, {"city": city.lower(), "fits_budget": grand_total <= total_budget})
    return {
        "venue_rental": round(venue_rental, 2),
        "venue_fees": round(venue_fees, 2),
        "catering": round(catering, 2),
        "catering_service_charge": round(service_charge, 2),
        "entertainment": round(entertainment_cost, 2),
        "sales_tax": round(tax, 2),
        "contingency_10pct": round(contingency, 2),
        "grand_total": round(grand_total, 2),
        "cost_per_guest": round(grand_total / guest_count, 2),
        "deposit_due_to_venue": round(venue_rental * venue_deposit_pct, 2),
        "fits_budget": grand_total <= total_budget,
        "headroom": round(total_budget - grand_total, 2),
    }


root_agent = Agent(
    name="budget_agent",
    model=CFG["model"],
    description=CFG["description"].strip(),
    instruction=CFG["instruction"],
    tools=[calculate_event_cost],
)

# A2A over HTTP (JSON-RPC, with SSE streaming advertised in the agent card).
# host/port only set the URL published in the card.
a2a_app = to_a2a(root_agent, host=config.PUBLIC_HOST, port=config.BUDGET_AGENT_PORT)
a2a_app.router.routes.append(health_route("budget_agent"))

# Extract the incoming W3C traceparent so this agent's spans join the caller's trace
instrument_app(a2a_app)