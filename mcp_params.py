import os
from dotenv import load_dotenv
from market import is_paid_polygon, is_realtime_polygon

load_dotenv(override=True)

brave_env = {"BRAVE_API_KEY": os.getenv("BRAVE_API_KEY")}
tavily_env = {"TAVILY_API_KEY": os.getenv("TAVILY_API_KEY")}

# Web-search provider for the Researcher sub-agent. Tavily is the default: it is
# agent-native and returns extracted page content (fewer follow-up fetches).
# Set SEARCH_PROVIDER=brave to use Brave's independent index instead.
SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "tavily").strip().lower()


def _search_mcp_server() -> dict | None:
    """MCP server config for the configured web-search provider.

    Returns None when the provider's API key is missing, so the Researcher runs
    without web search (it still has fetch + memory) instead of the whole trader
    run crashing on a None env value.
    """
    if SEARCH_PROVIDER == "brave":
        if not brave_env["BRAVE_API_KEY"]:
            print("[mcp_params][WARN] BRAVE_API_KEY is not set; researcher runs without web search")
            return None
        return {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-brave-search"],
            "env": brave_env,
        }
    if SEARCH_PROVIDER != "tavily":
        print(f"[mcp_params] Unknown SEARCH_PROVIDER={SEARCH_PROVIDER!r}; defaulting to tavily")
    if not tavily_env["TAVILY_API_KEY"]:
        print("[mcp_params][WARN] TAVILY_API_KEY is not set; researcher runs without web search")
        return None
    return {
        "command": "npx",
        "args": ["-y", "tavily-mcp"],
        "env": tavily_env,
    }

alpaca_env = {
    "ALPACA_API_KEY": os.getenv("ALPACA_API_KEY"),
    "ALPACA_SECRET_KEY": os.getenv("ALPACA_SECRET_KEY"),
    "ALPACA_PAPER": os.getenv("ALPACA_PAPER", "true"), # Default to Paper
    # The order server calls the JEV decision gate (jev.py) via OpenRouter.
    "OPENROUTER_API_KEY": os.getenv("OPENROUTER_API_KEY", ""),
}
# Pass JEV_*/FUNDING_* settings through only when set, so the modules' defaults apply otherwise.
alpaca_env.update({k: v for k, v in os.environ.items() if k.startswith(("JEV_", "FUNDING_"))})

polygon_api_key = os.getenv("POLYGON_API_KEY")

# Hardened, in-repo Alpaca execution server. Replaces the third-party
# `alpaca-mcp-server` so that every order mutation runs through our own code,
# which adds idempotency keys, retries with backoff, and bounded fill polling
# (see alpaca_exec.py). Credentials are inherited from the parent process env
# (already loaded above), same as the other local `uv run` servers.
alpaca_mcp = {
    "command": "uv",
    "args": ["run", "alpaca_exec_server.py"],
    "env": alpaca_env,
}

# The MCP server for the Trader to read Market Data

if is_paid_polygon or is_realtime_polygon:
    market_mcp = {
        "command": "uvx",
        "args": ["--from", "git+https://github.com/polygon-io/mcp_polygon@v0.1.0", "mcp_polygon"],
        "env": {"POLYGON_API_KEY": polygon_api_key},
    }
else:
    market_mcp = {"command": "uv", "args": ["run", "market_server.py"]}


# The full set of MCP servers for the trader: Accounts, Push Notification and the Market

trader_mcp_server_params = [
    {"command": "uv", "args": ["run", "accounts_server.py"]},
    {"command": "uv", "args": ["run", "push_server.py"]},
    market_mcp,
    alpaca_mcp
]

# The full set of MCP servers for the researcher: Fetch, Brave Search and Memory


def researcher_mcp_server_params(name: str):
    servers = [
        {"command": "uvx", "args": ["mcp-server-fetch"]},
        _search_mcp_server(),
        {
            "command": "npx",
            "args": ["-y", "mcp-memory-libsql"],
            "env": {"LIBSQL_URL": f"file:./memory/{name}.db"},
        },
    ]
    return [s for s in servers if s is not None]
