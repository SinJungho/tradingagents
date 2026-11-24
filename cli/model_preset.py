"""Per-command GPT presets for the research harness."""

import os
from contextlib import contextmanager
from enum import StrEnum
from typing import Annotated

import typer

from tradingagents.default_config import _ENV_OVERRIDES, DEFAULT_CONFIG
from tradingagents.llm_clients.factory import tier_provider


class ModelPreset(StrEnum):
    STANDARD = "standard"
    DEEP = "deep"


@contextmanager
def _preset_settings(preset: ModelPreset):
    deep = preset == ModelPreset.DEEP
    settings = {"openai_reasoning_effort": "high" if deep else "medium"}
    for tier, model in (("quick", "gpt-6.2-sol" if deep else "gpt-6-luna"), ("deep", "gpt-6.1-sol")):
        if tier_provider(DEFAULT_CONFIG, tier) in ("openai", "chatgpt"):
            settings[f"{tier}_think_llm"] = model
    env = {name: settings[key] for name, key in _ENV_OVERRIDES.items() if key in settings}
    previous_config = {key: DEFAULT_CONFIG[key] for key in settings}
    previous_env = {name: os.environ.get(name) for name in env}
    try:
        DEFAULT_CONFIG.update(settings)
        os.environ.update(env)
        yield
    finally:
        DEFAULT_CONFIG.update(previous_config)
        for name, value in previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _apply_preset(ctx: typer.Context, value: ModelPreset | None) -> ModelPreset | None:
    if value is not None and not ctx.resilient_parsing:
        ctx.with_resource(_preset_settings(value))
    return value


ModelPresetOption = Annotated[
    ModelPreset | None,
    typer.Option("--model-preset", callback=_apply_preset, help="GPT preset for this run."),
]
