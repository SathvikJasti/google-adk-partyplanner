import math
from datetime import date
from pathlib import Path

from common import config
from common.telemetry import instrument_app, setup_telemetry

setup_telemetry("compliance_agent")  # before ADK is imported

import yaml
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import Agent
from opentelemetry import metrics

from common.health import health_route

CFG = yaml.safe_load((Path(__file__).parent / "instructions.yaml").read_text(encoding="utf-8"))

CHECKS = metrics.get_meter("compliance_agent").create_counter(
    "compliance_checks", description="Compliance checks run, by city and resulting status"
)

# Mock city rules. NOT real legal advice.
CITY_RULES = {
    "new york": {"outdoor_music_cutoff": "22:00", "permit_guest_threshold": 75,
                 "permit_lead_days": 21, "kids_per_adult": 8},
    "austin":   {"outdoor_music_cutoff": "22:00", "permit_guest_threshold": 100,
                 "permit_lead_days": 14, "kids_per_adult": 10},
    "chicago":  {"outdoor_music_cutoff": "23:00", "permit_guest_threshold": 80,
                 "permit_lead_days": 14, "kids_per_adult": 8},
}


def get_city_rules(city: str) -> dict:
    """Return the event rules for a city: outdoor amplified-music cutoff, the guest
    count above which an event permit is needed, permit lead time in days, and the
    kids-per-adult supervision ratio."""
    rules = CITY_RULES.get(city.lower())
    return rules or {"error": f"No rules on file for {city}."}


def check_event_compliance(
    city: str,
    event_date: str,
    start_time: str,
    end_time: str,
    guest_count: int,
    age_group: str,
    serves_alcohol: bool,
    venue_alcohol_allowed: bool,
    venue_indoor: bool,
    venue_curfew: str,
) -> dict:
    """Check one proposed event against city and venue rules. Times use 24-hour
    HH:MM format and the event must end the same day (by 23:59). Returns a status
    (clear, action_needed, blocked) and a list of issues with severity."""
    rules = CITY_RULES.get(city.lower())
    if not rules:
        return {"status": "unknown", "issues": [{"severity": "info", "message": f"No rules on file for {city}."}]}
    try:
        days_until = (date.fromisoformat(event_date) - date.today()).days
    except ValueError:
        return {"error": "event_date must be YYYY-MM-DD."}

    issues = []

    # Events end by 23:59, so a curfew after midnight (e.g. 01:00) can't be hit.
    if end_time > venue_curfew and venue_curfew >= "12:00":
        issues.append({"severity": "blocker",
                       "message": f"Event ends {end_time} but the venue curfew is {venue_curfew}."})
    if not venue_indoor and end_time > rules["outdoor_music_cutoff"]:
        issues.append({"severity": "action",
                       "message": f"Outdoor amplified music must stop by {rules['outdoor_music_cutoff']}; "
                                  f"plan an indoor area or end music earlier."})
    if guest_count > rules["permit_guest_threshold"]:
        if days_until < rules["permit_lead_days"]:
            issues.append({"severity": "blocker",
                           "message": f"Events over {rules['permit_guest_threshold']} guests need a permit "
                                      f"{rules['permit_lead_days']} days ahead; only {days_until} days remain."})
        else:
            issues.append({"severity": "action",
                           "message": f"Apply for an event permit at least {rules['permit_lead_days']} days "
                                      f"before the event (over {rules['permit_guest_threshold']} guests)."})
    if serves_alcohol and not venue_alcohol_allowed:
        issues.append({"severity": "blocker", "message": "The venue does not allow alcohol."})
    if serves_alcohol and age_group.lower() in ("kids", "teens"):
        issues.append({"severity": "blocker", "message": "Alcohol cannot be served at an event for minors."})
    if age_group.lower() == "kids":
        adults = math.ceil(guest_count / rules["kids_per_adult"])
        issues.append({"severity": "action",
                       "message": f"Kids' event: arrange at least {adults} supervising adults "
                                  f"(1 per {rules['kids_per_adult']} children)."})

    if any(i["severity"] == "blocker" for i in issues):
        status = "blocked"
    elif issues:
        status = "action_needed"
    else:
        status = "clear"
    CHECKS.add(1, {"city": city.lower(), "status": status})
    return {"status": status, "days_until_event": days_until, "issues": issues}


root_agent = Agent(
    name="compliance_agent",
    model=CFG["model"],
    description=CFG["description"].strip(),
    instruction=CFG["instruction"],
    tools=[get_city_rules, check_event_compliance],
)

# A2A over HTTP (JSON-RPC, with SSE streaming advertised in the agent card).
# host/port only set the URL published in the card.
a2a_app = to_a2a(root_agent, host=config.PUBLIC_HOST, port=config.COMPLIANCE_AGENT_PORT)
a2a_app.router.routes.append(health_route("compliance_agent"))

# Extract the incoming W3C traceparent so this agent's spans join the caller's trace
instrument_app(a2a_app)