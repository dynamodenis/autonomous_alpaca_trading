from mcp.server.fastmcp import FastMCP
from accounts import Account

mcp = FastMCP("accounts_server")


@mcp.tool()
async def update_buy_account_holdings_transactions(
    name: str, symbol: str, quantity: int, rationale: str, price: float
) -> dict[str, str]:
    """Update account holdings when you buy shares for the specific account."""
    print(f"update transactions for {symbol}")

    account = Account.get(name)
    account.update_holdings_and_transactions(
        "buy", symbol, quantity, rationale, price
    )
    account.save()  # ← Ensure save is called
    return {"status": "ok", "message": f"Updated holding {symbol} "}

@mcp.tool()
async def update_sell_account_holdings_transactions(
    name: str, symbol: str, quantity: int, rationale: str, price: float
) -> dict[str, str]:
    """Update account holdings when you sell shares for the specific account."""

    print(f"update transactions for {symbol}")
    account = Account.get(name)
    account.update_holdings_and_transactions(
        "sell", symbol, quantity, rationale, price
    )
    account.save()  # ← Ensure save is called
    return {"status": "ok", "message": f"Updated holding {symbol} "}

@mcp.tool()
async def update_log_trade(name: str, type: str, message: str) -> str:
    """
    Write a log entry to the logs table.

    Args:
        name: Account name (string)
        type: Log type, e.g. "BUY", "SELL", "ERROR", "STRATEGY"
        message: A descriptive message explaining the activity
    """
    Account.write_log(name, type, message)
    return "ok"


@mcp.tool()
async def get_strategy(name: str) -> str:
    acct = Account.get(name)
    return acct.get_strategy()


@mcp.tool()
async def change_strategy(name: str, strategy: str) -> str:
    """At your discretion, if you choose to, call this to change your investment strategy for the future.

    Args:
        name: The name of the account holder
        strategy: The new strategy for the account
    """
    return Account.get(name).change_strategy(strategy)


@mcp.resource("accounts://accounts_server/{name}")
async def read_account_resource(name: str) -> str:
    account = Account.get(name.lower())
    return account.report()


@mcp.resource("accounts://strategy/{name}")
async def read_strategy_resource(name: str) -> str:
    account = Account.get(name.lower())
    return account.get_strategy()


if __name__ == "__main__":
    mcp.run(transport="stdio")
