"""
JEV decision gate for trader orders.

The trader agent (a tool-calling chat model) researches and *proposes* each
order; before it reaches Alpaca, JEV decides whether it executes. JEV is not a
chat model: it answers typed multiple-choice questions over a given state, via
OpenRouter's Decisions API (POST /api/alpha/decisions) with the normal
OPENROUTER_API_KEY. That makes it a cheap (~$0.00002/call) approve/reject judge.

Config (env):
    JEV_ENABLED       "true" (default) to gate every order through JEV
    JEV_MODEL         pinned JEV release
    JEV_MIN_APPROVE   minimum P(approve) required to execute (default 0.6)
    JEV_FAIL_OPEN     "true" to let orders through when JEV itself errors
                      (default false: no verdict -> no trade)
"""

import os

import httpx
from dotenv import load_dotenv

load_dotenv(override=True)

JEV_ENABLED = os.getenv("JEV_ENABLED", "true").strip().lower() == "true"
JEV_MODEL = os.getenv("JEV_MODEL", "typesafe/jev-1.13-20260917")
JEV_MIN_APPROVE = float(os.getenv("JEV_MIN_APPROVE", "0.6"))
JEV_FAIL_OPEN = os.getenv("JEV_FAIL_OPEN", "false").strip().lower() == "true"

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
TIMEOUT_SECONDS = 30.0

EXECUTE_QUESTION = {
    "type": "choice",
    "instructions": (
        "You are the risk and decision gate for an autonomous trading agent. "
        "Given the trader's strategy, the proposed order, its rationale, the account "
        "and the current position, decide whether this order should be executed."
    ),
    "criteria": {
        "approve": (
            "Either the order reduces risk (e.g. a sell that cuts leverage, negative cash "
            "or concentration, or exits a position whose thesis no longer holds), or it is "
            "a specific, evidence-backed opportunity consistent with the strategy whose "
            "size is prudent for the account (fits buying power, no reckless leverage)."
        ),
        "reject": (
            "The rationale is vague, speculative or unsupported, the order contradicts the "
            "strategy, or it adds risk imprudently (exceeds buying power, over-concentrates, "
            "or increases leverage on an already leveraged account)."
        ),
    },
}


def _validate(answer: dict) -> str:
    """Return "" for a well-formed choice answer, else the reason (mirrors orbiter's check)."""
    criteria = EXECUTE_QUESTION["criteria"]
    probs = answer.get("probabilities") or {}
    if answer.get("type") != "choice" or answer.get("choice") not in criteria:
        return "malformed"
    if set(probs) != set(criteria) or abs(sum(probs.values()) - 1) > 0.02:
        return "invalid_probabilities"
    return ""


async def judge_order(state: dict) -> dict:
    """Ask JEV whether to execute the order described by `state`.

    Returns {"approved": bool, "choice", "p_approve", "confidence", "id", "cost",
    "reason"}. Exactly one HTTP attempt — each call is billed, and a rejected
    or failed verdict is final for this order.
    """
    body = {"model": JEV_MODEL, "state": state, "questions": {"execute": EXECUTE_QUESTION}}
    headers = {"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY', '')}"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.post(DECISIONS_URL, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        answer = (data.get("answers") or {}).get("execute") or {}
        problem = _validate(answer)
        if problem:
            raise ValueError(f"JEV answer {problem}: {answer}")
    except Exception as exc:  # noqa: BLE001 - any failure falls back to JEV_FAIL_OPEN
        return {
            "approved": JEV_FAIL_OPEN,
            "choice": None,
            "reason": f"JEV call failed ({exc}); {'fail-open' if JEV_FAIL_OPEN else 'fail-closed'}",
        }

    p_approve = float(answer["probabilities"]["approve"])
    approved = answer["choice"] == "approve" and p_approve >= JEV_MIN_APPROVE
    return {
        "approved": approved,
        "choice": answer["choice"],
        "p_approve": round(p_approve, 3),
        "confidence": answer.get("confidence"),
        "id": data.get("id"),
        "cost": (data.get("usage") or {}).get("cost"),
        "reason": (
            f"{answer['choice']} with P(approve)={p_approve:.2f} "
            f"(min {JEV_MIN_APPROVE:.2f})"
        ),
    }
