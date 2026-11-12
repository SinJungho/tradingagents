"""Prompt contracts for traceable claims and holdings-aware recommendations."""

import importlib
import inspect

import pytest

from tradingagents.agents.context import (
    get_evidence_instruction,
    get_position_blind_instruction,
    get_position_instruction,
)
from tradingagents.agents.schemas import PortfolioDecision, TraderProposal

REPORT_AGENTS = (
    "tradingagents.agents.analysts.market_analyst",
    "tradingagents.agents.analysts.fundamentals_analyst",
    "tradingagents.agents.analysts.news_analyst",
    "tradingagents.agents.analysts.sentiment_analyst",
    "tradingagents.agents.researchers.bull_researcher",
    "tradingagents.agents.researchers.bear_researcher",
    "tradingagents.agents.managers.research_manager",
    "tradingagents.agents.trader.trader",
    "tradingagents.agents.risk_mgmt.aggressive_debator",
    "tradingagents.agents.risk_mgmt.conservative_debator",
    "tradingagents.agents.risk_mgmt.neutral_debator",
    "tradingagents.agents.managers.portfolio_manager",
)

POSITION_AWARE_AGENTS = (
    "tradingagents.agents.trader.trader",
    "tradingagents.agents.managers.portfolio_manager",
    "tradingagents.agents.risk_mgmt.aggressive_debator",
    "tradingagents.agents.risk_mgmt.conservative_debator",
    "tradingagents.agents.risk_mgmt.neutral_debator",
)

POSITION_BLIND_AGENTS = (
    "tradingagents.agents.researchers.bull_researcher",
    "tradingagents.agents.researchers.bear_researcher",
    "tradingagents.agents.managers.research_manager",
)


@pytest.mark.unit
def test_evidence_rule_requires_traceable_and_calculable_values():
    instruction = get_evidence_instruction()

    assert "source" in instruction
    assert "as-of time/date" in instruction
    assert "inputs and calculation" in instruction
    assert "unverified" in instruction
    assert "Do not create or repeat unsupported" in instruction


@pytest.mark.unit
def test_position_rules_distinguish_long_flat_short_and_unknown():
    instruction = get_position_instruction()

    assert "positive quantity is long" in instruction
    assert "negative quantity is short" in instruction
    assert "no current position" in instruction
    assert "covering/reducing" in instruction
    assert "holdings are not provided or are unknown" in instruction
    assert "You do not receive the caller's portfolio" in get_position_blind_instruction()


@pytest.mark.unit
@pytest.mark.parametrize("module_name", REPORT_AGENTS)
def test_every_report_agent_adds_the_evidence_rule(module_name):
    source = inspect.getsource(importlib.import_module(module_name))

    assert "get_evidence_instruction()" in source


@pytest.mark.unit
@pytest.mark.parametrize("module_name", POSITION_AWARE_AGENTS)
def test_agents_with_holdings_apply_position_aware_language(module_name):
    source = inspect.getsource(importlib.import_module(module_name))

    assert "get_position_instruction()" in source


@pytest.mark.unit
@pytest.mark.parametrize("module_name", POSITION_BLIND_AGENTS)
def test_research_agents_do_not_assume_holdings(module_name):
    source = inspect.getsource(importlib.import_module(module_name))

    assert "get_position_blind_instruction()" in source


@pytest.mark.unit
def test_price_fields_require_supplied_basis_and_allow_omission():
    entry = TraderProposal.model_fields["entry_price"].description.lower()
    stop = TraderProposal.model_fields["stop_loss"].description.lower()
    target = PortfolioDecision.model_fields["price_target"].description.lower()

    assert "supplied market data supports" in entry
    assert "otherwise omit it" in stop
    assert "explicit calculation basis" in target
