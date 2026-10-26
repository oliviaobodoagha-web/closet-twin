"""Day Planner: today's calendar + weather + closet -> outfit blocks for the day."""

from __future__ import annotations

from .. import memory, store
from .. import safety
from ..ledger import Ledger
from ..llm import Tool, obj_schema, run_agent
from ..tools import weather
from .. import stylists
from .common import closet_brief, instructions, profile_brief

# Measured in tests/cost_experiments.py: see docs/cost_experiments.json.
PLANNER_EFFORT = "low"
DAY_PLAN_EFFORT = "medium"  # the full day (main pick + alternates) needs the extra thinking; low gave clashing options

PLAN_SCHEMA = obj_schema({
    "headline": {"type": "string"},
    "stylist_take": {"type": "string"},
    "weather_note": {"type": "string"},
    "blocks": {"type": "array", "items": obj_schema({
        "start": {"type": "string"},
        "end": {"type": "string"},
        "label": {"type": "string"},
        "scene": {"type": "string", "enum": ["gym", "classroom", "office", "coffee", "street", "dinner"]},
        "events": {"type": "array", "items": {"type": "string"}},
        "item_ids": {"type": "array", "items": {"type": "string"}},
        "change_note": {"type": "string"},
        "why": {"type": "string"},
        "stylist_note": {"type": "string"},
        # other complete outfits for the same block; she can pick one instead (no model call)
        "alternates": {"type": "array", "items": obj_schema({
            "title": {"type": "string"},
            "item_ids": {"type": "array", "items": {"type": "string"}},
            "why": {"type": "string"},
        })},
    })},
})


def plan_tools(dataset: str, day: str) -> list[Tool]:
    prof = store.profile(dataset)

    def get_calendar(date: str) -> dict:
        # Live iCal link or uploaded .ics; the sample calendar is one example day shown on any date.
        events, source = store.day_events(dataset, date)
        return {"date": date, "source": source, "events": events}

    def get_weather(date: str) -> dict:
        w = weather.forecast(prof.get("lat", 41.31), prof.get("lon", -72.93), date)
        w["season"] = weather.season_for(date, prof.get("lat", 41.31))
        return w

    date_param = obj_schema({"date": {"type": "string", "description": "YYYY-MM-DD"}})
    return [
        Tool("get_calendar", "The user's events for a date (titles, times, places).", date_param, get_calendar),
        Tool("get_weather", "Forecast for the user's city on a date: high/low, rain chance, hourly feels-like.", date_param, get_weather),
    ]


def wearable(dataset: str) -> list[dict]:
    """What can go in today's outfit: not returned, not packed away as out of season."""
    return [i for i in store.closet(dataset) if i.get("status") != "returned" and not i.get("out_of_season")]


def plan_day(ledger: Ledger, dataset: str, day: str, feedback: list[str] | None = None, previous: dict | None = None) -> dict:
    closet = wearable(dataset)
    prof = store.profile(dataset)
    # Stable prefix first (closet + style), changing parts last, so repeat runs hit the prompt cache.
    content = (
        f"MY CLOSET:\n{closet_brief(closet)}\n\nABOUT ME:\n{profile_brief(prof, include_body=False)}\n\n"
        f"{stylists.point_of_view(prof, dataset)}\n\n{memory.brief(dataset, day)}\n\nPlan my outfits for {day}."
    )
    tools = plan_tools(dataset, day)
    if feedback:
        # Revisions reuse the calendar and weather instead of calling the tools again (one model turn saved).
        cal = tools[0].fn(day)
        wx = tools[1].fn(day)
        content += f"\n\nCALENDAR: {cal}\nWEATHER: {wx}"
        content += "\n\nThe Style Critic sent your last plan back. Fix these points:\n- " + "\n- ".join(feedback)
        content += f"\nYour last plan was: {previous}"
        tools = []
    ledger.step("Day Planner", "start", f"Planning {day}" + (" (revision)" if feedback else ""))
    result = run_agent(
        ledger, "Day Planner", instructions("planner"), content,
        schema=PLAN_SCHEMA, schema_name="day_plan", tools=tools, effort=DAY_PLAN_EFFORT,
    )
    plan = result.output
    ledger.step("Day Planner", "done", f"{len(plan['blocks'])} outfit block(s): " + "; ".join(b["label"] for b in plan["blocks"]))
    return plan


BLOCK_SCHEMA = PLAN_SCHEMA["properties"]["blocks"]["items"]


def swap_block(ledger: Ledger, dataset: str, day: str, block: dict, reason: str = "") -> dict:
    """'Show me another option': one new outfit for the same block, never the one she just turned down."""
    closet = wearable(dataset)
    prof = store.profile(dataset)
    reason, _ = safety.clean_untrusted(reason or "", 200)
    content = (
        f"MY CLOSET:\n{closet_brief(closet)}\n\nABOUT ME:\n{profile_brief(prof, include_body=False)}\n\n"
        f"{stylists.point_of_view(prof, dataset)}\n\n{memory.brief(dataset, day)}\n\n"
        f"Today is {day}. I turned down this outfit for '{block.get('label')}' ({block.get('start')}-{block.get('end')}, "
        f"events: {block.get('events')}, scene {block.get('scene')}): {block.get('item_ids')}."
        + (f" Why: {safety.fence('user note', reason)}" if reason else "")
        + " Give me ONE different outfit for the same block: change at least the main pieces, keep it right for the events and weather. "
          "Do not call tools; plan from what you know."
    )
    ledger.step("Day Planner", "start", f"Another option for '{block.get('label')}'")
    result = run_agent(ledger, "Day Planner", instructions("planner"), content,
                       schema=BLOCK_SCHEMA, schema_name="outfit_block", effort=PLANNER_EFFORT)
    new = result.output
    by_id = {i["id"]: i for i in closet}
    new["item_ids"] = [i for i in new["item_ids"] if i in by_id]
    new["items"] = [by_id[i] for i in new["item_ids"]]
    ledger.step("Day Planner", "done", f"New option: {', '.join(i['name'] for i in new['items'])}")
    return new
