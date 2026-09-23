"""
Live funding state of the shared Alpaca account, for the trader prompts.

All traders trade one Alpaca account, but each keeps its own SQLite ledger,
whose `balance` is a synced copy of the account's total value and whose
holdings miss anything bought before the ledger started. Deciding from that
made every trader believe it had the whole account in cash. This module reads
the real cash and positions from Alpaca and turns them into a funding mode
with a concrete per-trader budget, so the prompt can say plainly whether to
sell first, rotate, or deploy cash.

Modes (thresholds are cash as a fraction of equity, set via env):
    RAISE_CASH  cash < 0                        -> sells only, cover a share of the shortfall
    ROTATE      0 <= cash < ROTATE_BELOW        -> sell a weaker position first, then buy with the proceeds
    NORMAL      ROTATE_BELOW <= cash <= DEPLOY_ABOVE
    DEPLOY      cash > DEPLOY_ABOVE             -> look for buys; don't sell just to sell
"""

import os

import alpaca_exec

ROTATE_BELOW = float(os.getenv("FUNDING_ROTATE_BELOW", "0.10"))
DEPLOY_ABOVE = float(os.getenv("FUNDING_DEPLOY_ABOVE", "0.30"))


def _f(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def funding_mode(cash: float, equity: float) -> str:
    """Classify the account by its cash as a fraction of equity."""
    if cash < 0:
        return "RAISE_CASH"
    ratio = cash / equity if equity > 0 else 0.0
    if ratio < ROTATE_BELOW:
        return "ROTATE"
    if ratio > DEPLOY_ABOVE:
        return "DEPLOY"
    return "NORMAL"


async def funding_snapshot(traders_remaining: int = 1) -> dict:
    """Read the live account and positions and compute this trader's mode and budget.

    `traders_remaining` counts this trader and those still to run this cycle, so
    the cash (or the shortfall) is split fairly as traders run one after another.
    """
    acct = await alpaca_exec.get_account_info()
    positions = await alpaca_exec.get_positions()
    cash, equity = _f(acct.get("cash")), _f(acct.get("equity"))
    share = max(1, traders_remaining)

    rows = []
    for p in positions:
        mv, upl = _f(p.get("market_value")), _f(p.get("unrealized_pl"))
        cost = mv - upl
        rows.append({
            "symbol": p.get("symbol"),
            "qty": _f(p.get("qty")),
            "market_value": round(mv, 2),
            "weight_pct": round(mv / equity * 100, 1) if equity > 0 else None,
            "unrealized_pl": round(upl, 2),
            "unrealized_pl_pct": round(upl / cost * 100, 1) if cost else None,
        })
    rows.sort(key=lambda r: abs(r["market_value"]), reverse=True)
    gross = sum(abs(r["market_value"]) for r in rows)

    mode = funding_mode(cash, equity)
    return {
        "mode": mode,
        "cash": round(cash, 2),
        "equity": round(equity, 2),
        "gross_exposure": round(gross, 2),
        "leverage": round(gross / equity, 2) if equity > 0 else None,
        # RAISE_CASH: how much this trader should sell. Otherwise: its cash budget.
        "sell_target": round(-cash / share, 2) if cash < 0 else 0.0,
        "buy_budget": round(cash / share, 2) if cash > 0 else 0.0,
        "traders_sharing": share,
        "positions": rows,
    }


_MODE_RULES = {
    "RAISE_CASH": (
        "The account has NEGATIVE cash (it is borrowing on margin). SELL FIRST: this cycle you "
        "may ONLY sell. Sell about ${sell_target:,.0f} of positions (your share of the shortfall), "
        "choosing those that fit your strategy worst: broken theses, oversized weights, weak "
        "momentum, or gains worth locking in. Do NOT place any buy orders — they will be blocked."
    ),
    "ROTATE": (
        "Cash is low (under {rotate:.0%} of equity). Only buy by ROTATING: first sell a weaker "
        "position, and after that sell has filled, buy with no more than its proceeds plus your "
        "${buy_budget:,.0f} budget. If nothing is worth rotating into, hold."
    ),
    "NORMAL": (
        "Cash is adequate. You may buy with up to ${buy_budget:,.0f} (your share of the cash), "
        "and sell positions whose thesis no longer holds. Never spend more than your budget."
    ),
    "DEPLOY": (
        "Cash is plentiful (over {deploy:.0%} of equity). Look for buys that fit your strategy, "
        "spending up to ${buy_budget:,.0f} (your share of the cash). Do not sell just to sell."
    ),
}


def funding_brief(snap: dict) -> str:
    """Render the snapshot as the prompt's funding section."""
    rule = _MODE_RULES[snap["mode"]].format(
        rotate=ROTATE_BELOW, deploy=DEPLOY_ABOVE, **snap,
    )
    lines = [
        f"FUNDING MODE: {snap['mode']}",
        rule,
        "",
        f"Shared account (live from Alpaca): cash ${snap['cash']:,.2f} | equity ${snap['equity']:,.2f} | "
        f"gross exposure ${snap['gross_exposure']:,.2f} | leverage {snap['leverage']}x",
        f"Budget is split between the {snap['traders_sharing']} trader(s) still to act this cycle. "
        "Ignore Alpaca's margin `buying_power` — cash is your budget.",
        "",
        "Open positions (symbol, qty, value, weight of equity, unrealized P/L):",
    ]
    for r in snap["positions"] or []:
        lines.append(
            f"  {r['symbol']}: {r['qty']:g} sh, ${r['market_value']:,.0f}, {r['weight_pct']}%, "
            f"P/L ${r['unrealized_pl']:,.0f} ({r['unrealized_pl_pct']}%)"
        )
    if not snap["positions"]:
        lines.append("  (none)")
    return "\n".join(lines)


UNAVAILABLE_BRIEF = (
    "FUNDING MODE: UNKNOWN\n"
    "The live account could not be read this cycle. Do NOT place buy orders; "
    "only sell if clearly required by your strategy."
)
