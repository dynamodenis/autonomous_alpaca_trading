from contextlib import AsyncExitStack
from accounts import Account
from accounts_client import read_accounts_resource, read_strategy_resource
from tracers import make_trace_id
from agents import Agent, Tool, Runner, OpenAIChatCompletionsModel, trace, function_tool
from openai import AsyncOpenAI
from dotenv import load_dotenv
import os
import json
from agents.mcp import MCPServerStdio
from templates import (
    researcher_instructions,
    trader_instructions,
    trade_message,
    rebalance_message,
    research_tool,
)
from mcp_params import trader_mcp_server_params, researcher_mcp_server_params

load_dotenv(override=True)

openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

MAX_TURNS = 10

# The Researcher sub-agent does web search + summarization, which is cheap,
# high-volume work — so it runs on its own (cheaper) model, independent of the
# trader's model. Override with RESEARCHER_MODEL (an OpenRouter "provider/model" id).
RESEARCHER_MODEL = os.getenv("RESEARCHER_MODEL", "openai/gpt-4.1-mini")

# Every trader runs through OpenRouter, which gives us access to models from
# OpenAI, DeepSeek, Google, xAI, etc. behind a single API key. Model names use
# OpenRouter's "provider/model" form, e.g. "openai/gpt-4.1-mini".
openrouter_client = AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=openrouter_api_key)


def get_model(model_name: str):
    return OpenAIChatCompletionsModel(model=model_name, openai_client=openrouter_client)


async def get_researcher(mcp_servers, model_name) -> Agent:
    researcher = Agent(
        name="Researcher",
        instructions=researcher_instructions(),
        model=get_model(model_name),
        mcp_servers=mcp_servers,
    )
    return researcher


def _log_researcher_cost(owner_name: str, model_name: str, result) -> None:
    """Log the Researcher sub-agent's turn count and token usage per call.

    The researcher runs as a tool with its own SDK context, so its tokens are NOT
    in the trader's totals — this logs them separately so the full cost is visible.
    """
    try:
        turns = len(result.raw_responses)
    except Exception:  # noqa: BLE001
        turns = -1
    usage = getattr(getattr(result, "context_wrapper", None), "usage", None)
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    total = getattr(usage, "total_tokens", 0) or 0
    msg = f"researcher turns={turns} tokens(in={inp}, out={out}, total={total}) model={model_name}"
    print(f"[cost][researcher] {owner_name}: {msg}")
    try:
        Account.write_log(owner_name, "research-cost", msg)
    except Exception as e:  # noqa: BLE001
        print(f"[cost] failed to write researcher cost log for {owner_name}: {e}")


async def get_researcher_tool(mcp_servers, model_name, owner_name: str) -> Tool:
    researcher = await get_researcher(mcp_servers, model_name)

    # Wrap the researcher manually (instead of researcher.as_tool) so we get its
    # RunResult back and can log token usage on every call.
    @function_tool(name_override="Researcher", description_override=research_tool())
    async def researcher_tool(query: str) -> str:
        result = await Runner.run(researcher, query, max_turns=MAX_TURNS)
        _log_researcher_cost(owner_name, model_name, result)
        return str(result.final_output)

    return researcher_tool


class Trader:
    def __init__(self, name: str, lastname="Trader", model_name="openai/gpt-4.1-mini"):
        self.name = name
        self.lastname = lastname
        self.agent = None
        self.model_name = model_name
        self.do_trade = True

    async def create_agent(self, trader_mcp_servers, researcher_mcp_servers) -> Agent:
        # Researcher runs on its own cheap model, not the trader's.
        tool = await get_researcher_tool(researcher_mcp_servers, RESEARCHER_MODEL, owner_name=self.name)
        self.agent = Agent(
            name=self.name,
            instructions=trader_instructions(self.name),
            model=get_model(self.model_name),
            tools=[tool],
            mcp_servers=trader_mcp_servers,
        )
        return self.agent

    async def get_account_report(self) -> str:
        account = await read_accounts_resource(self.name)
        account_json = json.loads(account)
        account_json.pop("portfolio_value_time_series", None)
        # Keep only recent transactions (last 10)
        transactions = account_json.get("transactions", [])
        if len(transactions) > 10:
            account_json["transactions"] = transactions[-10:]
            account_json["total_transactions"] = len(transactions)  # Track total count
        
        return json.dumps(account_json)

    async def run_agent(self, trader_mcp_servers, researcher_mcp_servers):
        self.agent = await self.create_agent(trader_mcp_servers, researcher_mcp_servers)
        account = await self.get_account_report()
        strategy = await read_strategy_resource(self.name)
        message = (
            trade_message(self.name, strategy, account)
            if self.do_trade
            else rebalance_message(self.name, strategy, account)
        )
        result = await Runner.run(self.agent, message, max_turns=MAX_TURNS)
        self._log_run_cost(result)

    def _log_run_cost(self, result):
        """Log this run's turn count and token usage so an expensive cycle is
        visible (in stdout and the dashboard logs) before the bill arrives.

        NOTE: the Researcher sub-agent runs as a tool with its own SDK context,
        so its tokens are tracked separately and are NOT included in these totals.
        """
        try:
            turns = len(result.raw_responses)
        except Exception:  # noqa: BLE001
            turns = -1
        usage = getattr(getattr(result, "context_wrapper", None), "usage", None)
        inp = getattr(usage, "input_tokens", 0) or 0
        out = getattr(usage, "output_tokens", 0) or 0
        total = getattr(usage, "total_tokens", 0) or 0
        msg = (f"turns={turns}/{MAX_TURNS} tokens(in={inp}, out={out}, total={total}) "
               f"model={self.model_name}")
        print(f"[cost] {self.name}: {msg}")
        if turns >= max(1, int(MAX_TURNS * 0.8)):
            print(f"[cost][WARN] {self.name} used {turns}/{MAX_TURNS} turns — near/at the "
                  f"cap; the agent may be looping or its output was truncated.")
        try:
            Account.write_log(self.name, "cost", msg)
        except Exception as e:  # noqa: BLE001
            print(f"[cost] failed to write cost log for {self.name}: {e}")

    async def run_with_mcp_servers(self):
        async with AsyncExitStack() as stack:
            trader_mcp_servers = [
                await stack.enter_async_context(
                    MCPServerStdio(params, client_session_timeout_seconds=120)
                )
                for params in trader_mcp_server_params
            ]

            async with AsyncExitStack() as stack:
                researcher_mcp_servers = [
                    await stack.enter_async_context(
                        MCPServerStdio(params, client_session_timeout_seconds=120)
                    )
                    for params in researcher_mcp_server_params(self.name)
                ]
                await self.run_agent(trader_mcp_servers, researcher_mcp_servers)

    async def run_with_trace(self):
        trace_name = f"{self.name}-trading" if self.do_trade else f"{self.name}-rebalancing"
        trace_id = make_trace_id(f"{self.name.lower()}")
        with trace(trace_name, trace_id=trace_id):
            await self.run_with_mcp_servers()

    async def run(self):
        try:
            await self.run_with_trace()
        except Exception as e:
            print(f"Error running trader {self.name}: {e}")
        self.do_trade = not self.do_trade
