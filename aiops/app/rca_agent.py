from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.config import get_settings

settings = get_settings()


class RCAState(TypedDict, total=False):
    incident: dict[str, Any]      # serialized incident + alerts
    facts: str                    # compacted evidence
    analysis: dict[str, Any]      # root cause + confidence + factors
    recommendations: list[str]
    result: dict[str, Any]        # final structured report


# --- LLM client ------------------------------------------------------------

async def _chat_json(system: str, user: str) -> dict[str, Any]:
    """Call the LLM and parse a JSON object from its reply."""
    if settings.mock_llm:
        return _mock_reply(user)

    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)

    async def _call(json_mode: bool):
        kwargs: dict[str, Any] = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return await client.chat.completions.create(**kwargs)

    try:
        resp = await _call(json_mode=True)
    except Exception:
        resp = await _call(json_mode=False)  # model/gateway rejected response_format

    content = resp.choices[0].message.content or "{}"
    content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"_raw": content}


def _mock_reply(user: str) -> dict[str, Any]:
    """Deterministic stand-in so the pipeline runs without a live LLM."""
    if "root cause" in user.lower():
        return {
            "root_cause": "Shared dependency degradation inferred from co-occurring alerts on the same service/cluster.",
            "confidence": 0.62,
            "contributing_factors": [
                "Multiple firing alerts within the correlation window",
                "Common service or cluster label across alerts",
            ],
        }
    return {
        "recommendations": [
            "Check the most-upstream failing service first; downstream alerts are likely symptoms.",
            "Inspect recent deploys/config changes on the affected service in the last 30 minutes.",
            "Verify connection-pool and resource saturation on the implicated component.",
        ]
    }


# --- Graph nodes -----------------------------------------------------------

def gather(state: RCAState) -> RCAState:
    inc = state["incident"]
    lines = [f"Incident: {inc['title']} (severity={inc['severity']}, service={inc.get('service')})"]
    lines.append(f"Alert count: {len(inc['alerts'])}")
    for a in inc["alerts"]:
        lines.append(
            f"- [{a['severity']}] {a['name']} service={a.get('service')} "
            f"labels={a.get('labels')} starts_at={a.get('starts_at')} count={a.get('count')}"
        )
    return {"facts": "\n".join(lines)}


async def analyze(state: RCAState) -> RCAState:
    system = (
        "You are an SRE root-cause analyst. Given correlated alerts for one incident, "
        "identify the single most likely root cause. Respond as a JSON object with keys "
        "root_cause (string), confidence (0-1 float), contributing_factors (string array)."
    )
    out = await _chat_json(system, f"Evidence:\n{state['facts']}\n\nDetermine the root cause.")
    return {"analysis": out}


async def recommend(state: RCAState) -> RCAState:
    system = (
        "You are an SRE. Given an incident and its root-cause analysis, produce concrete "
        "remediation steps. Respond as a JSON object with key recommendations (string array)."
    )
    out = await _chat_json(
        system,
        f"Evidence:\n{state['facts']}\n\nAnalysis:\n{json.dumps(state['analysis'])}",
    )
    recs = out.get("recommendations", [])
    analysis = state["analysis"]
    result = {
        "root_cause": analysis.get("root_cause", "Undetermined"),
        "confidence": float(analysis.get("confidence", 0.0) or 0.0),
        "contributing_factors": analysis.get("contributing_factors", []),
        "recommendations": recs,
        "summary": (
            f"{analysis.get('root_cause', 'Undetermined')} "
            f"(confidence {float(analysis.get('confidence', 0.0) or 0.0):.0%})."
        ),
        "model": "mock" if settings.mock_llm else settings.llm_model,
    }
    return {"recommendations": recs, "result": result}


def build_rca_graph():
    g = StateGraph(RCAState)
    g.add_node("gather", gather)
    g.add_node("analyze", analyze)
    g.add_node("recommend", recommend)
    g.set_entry_point("gather")
    g.add_edge("gather", "analyze")
    g.add_edge("analyze", "recommend")
    g.add_edge("recommend", END)
    return g.compile()


_GRAPH = build_rca_graph()


async def run_rca(incident: dict[str, Any]) -> dict[str, Any]:
    final = await _GRAPH.ainvoke({"incident": incident})
    return final["result"]
