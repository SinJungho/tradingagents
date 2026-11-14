<p align="center">
  <img src="tradingagents/assets/tauric-logo.svg" width="60%" alt="Tauric Research">
</p>

# TradingAgents: Multi-Agents LLM Financial Trading Framework

<div align="center" style="line-height: 1;">
  <a href="https://arxiv.org/abs/2412.20138" target="_blank"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="https://discord.com/invite/hk9PGKShPK" target="_blank"><img alt="Discord" src="https://img.shields.io/badge/Discord-TradingResearch-7289da?logo=discord&logoColor=white&color=7289da"/></a>
  <a href="https://x.com/TauricResearch" target="_blank"><img alt="X Follow" src="https://img.shields.io/badge/X-TauricResearch-white?logo=x&logoColor=white"/></a>
  <a href="https://github.com/TauricResearch/" target="_blank"><img alt="Community" src="https://img.shields.io/badge/GitHub_Community-TauricResearch-14C290?logo=discourse"/></a>
</div>

<br>
<div align="center">
  <a href="https://github.com/TauricResearch" target="_blank"><img alt="TradingAgents #1 Repository of the Day" src="https://trendshift.io/api/badge/repositories/16192" width="250" height="55"/></a>
</div>

## Latest: [Trading-R1](https://github.com/TauricResearch/Trading-R1) is now in early access

After so many requests from the community, Trading-R1 has officially launched!

<p align="center">
  <a href="https://github.com/TauricResearch/Trading-R1" target="_blank"><img src="https://raw.githubusercontent.com/TauricResearch/Trading-R1/main/assets/trading-r1.gif" alt="Trading-R1 answering a research question in the terminal" width="100%"></a>
</p>

<h3 align="center"><a href="https://github.com/TauricResearch/Trading-R1" target="_blank">Register for early access ↗</a></h3>

## News

<!-- news:start -->
- [2026-11] **Trading-R1 v0.1.0** released, and [early access](https://github.com/TauricResearch/Trading-R1) is open.
- [2026-10] **TradingAgents v0.7.1** released with decisions scored only on final closes and settled across long market holidays, a fix for model dates that could read filings made after the run date, and fixes to portfolios, prices, SEC statements and reports.
- [2026-10] **TradingAgents v0.7.0** released with runs on your own ChatGPT Plus or Pro plan, backtests scored from the first close after each decision, a note at start-up when a newer release is out, and a wheel attached to each GitHub release.

<details>
<summary>Earlier news</summary>

- [2026-10] **TradingAgents v0.6.0** released with reports saved as one HTML page, a provider per model tier so the managers and analysts can run on different models, past decisions settled for every ticker while the analysts work, and company news read from Yahoo search while Yahoo's news feed is down.
- [2026-09] **TradingAgents v0.5.2** released with parallel analysts for a faster analysis, a CLI that runs without prompts from flags such as `--ticker` and `--date`, the run's settings recorded in every report, and backtests that see only data published by each analysis date.
- [2026-09] **TradingAgents v0.5.1** released with a package layout organised by what each module holds (import paths moved), optional Jev screening of social posts, GPT-6 Sol and Luna as the default models, and fixes to run isolation and SEC EDGAR statements.
- [2026-09] **TradingAgents v0.5.0** released with point-in-time integrity across every dated path, SEC EDGAR fundamentals served as filed, backtesting over a ticker and date grid, portfolio-aware runs, and current model lineups across every provider.
- [2026-08] **TradingAgents v0.4.0** released with look-ahead / point-in-time fixes across FRED macro, social sentiment, and the decision-log memory; clearer decision signals; working CLI checkpoint resume; Trader price grounding; and the GPT-5.6 and GLM-5.3 models.
- [2026-07] **TradingAgents v0.3.1** released with correctness and stability fixes: Alpha Vantage look-ahead filtering, graph-router crash-safety, graph-shape-aware checkpoint resume, working crypto sentiment sources, a configurable LLM retry budget, Bedrock API-key auth, and Claude Sonnet 5 / Fable 5 support.
- [2026-06] **TradingAgents v0.3.0** released with a verified data-access contract, an expanded provider registry (NVIDIA, Kimi, Groq, Mistral, Bedrock, and any OpenAI-compatible endpoint), FRED and Polymarket data vendors, a current-generation model catalog, and a CI gate.
- [2026-05] **TradingAgents v0.2.5** released with the grounded Sentiment Analyst, GPT-5.5 etc. model coverage, Qwen/GLM/MiniMax dual-region support, `TRADINGAGENTS_*` env-var configurability with API-key auto-detection, remote Ollama support, non-US alpha benchmarks, and ticker path-traversal hardening.
- [2026-04] **TradingAgents v0.2.4** released with structured-output agents (Research Manager, Trader, Portfolio Manager), LangGraph checkpoint resume, persistent decision log, DeepSeek/Qwen/GLM/Azure provider support, Docker, and a Windows UTF-8 encoding fix.
- [2026-03] **TradingAgents v0.2.3** released with multi-language support, GPT-5.4 family models, unified model catalog, backtesting date fidelity, and proxy support.
- [2026-03] **TradingAgents v0.2.2** released with GPT-5.4/Gemini 3.1/Claude 4.6 model coverage, five-tier rating scale, OpenAI Responses API, Anthropic effort control, and cross-platform stability.
- [2026-02] **TradingAgents v0.2.0** released with multi-provider LLM support (GPT-5.x, Gemini 3.x, Claude 4.x, Grok 4.x) and improved system architecture.
- [2026-01] **Trading-R1** [Technical Report](https://arxiv.org/abs/2509.11420) released, with [Terminal](https://github.com/TauricResearch/Trading-R1) expected to land soon.

</details>
<!-- news:end -->

<div align="center">

🚀 [TradingAgents](#tradingagents-framework) | ⚡ [Installation & CLI](#installation-and-cli) | 🎬 [Demo](https://www.youtube.com/watch?v=90gr5lwjIho) | 📦 [Package Usage](#tradingagents-package) | 🤝 [Contributing](#contributing) | 📄 [Citation](#citation)

</div>

> 🎉 **TradingAgents** officially released! We have received numerous inquiries about the work, and we would like to express our thanks for the enthusiasm in our community.
>
> So we decided to fully open-source the framework. Looking forward to building impactful projects with you!

## TradingAgents Framework

TradingAgents is a multi-agent trading framework that mirrors the dynamics of real-world trading firms. By deploying specialized LLM-powered agents: from fundamental analysts, sentiment experts, and technical analysts, to trader, risk management team, the platform collaboratively evaluates market conditions and informs trading decisions. Moreover, these agents engage in dynamic discussions to pinpoint the optimal strategy.

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> TradingAgents framework is designed for research purposes. Trading performance may vary based on many factors, including the chosen backbone language models, model temperature, trading periods, the quality of data, and other non-deterministic factors. [It is not intended as financial, investment, or trading advice.](https://tauric.ai/disclaimer/)

Our framework decomposes complex trading tasks into specialized roles.

### Analyst Team
- Fundamentals Analyst: Evaluates company financials and performance metrics, identifying intrinsic values and potential red flags.
- Sentiment Analyst: Aggregates news headlines, StockTwits, and Reddit chatter into a single sentiment read to gauge short-term market mood.
- News Analyst: Monitors global news and macroeconomic indicators, interpreting the impact of events on market conditions.
- Technical Analyst: Utilizes technical indicators (like MACD and RSI) to detect trading patterns and forecast price movements.

The selected analysts work at the same time, each on its own tools, and the research debate starts once all of their reports are in.

<p align="center">
  <img src="assets/analyst.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### Researcher Team
- Comprises both bullish and bearish researchers who critically assess the insights provided by the Analyst Team. Through structured debates, they balance potential gains against inherent risks.

<p align="center">
  <img src="assets/researcher.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Trader Agent
- Composes reports from the analysts and researchers to make informed trading decisions, determining the timing and magnitude of trades.

<p align="center">
  <img src="assets/trader.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Risk Management and Portfolio Manager
- Continuously evaluates portfolio risk by assessing market volatility, liquidity, and other risk factors. The risk management team evaluates and adjusts trading strategies, providing assessment reports to the Portfolio Manager for final decision.
- The Portfolio Manager approves/rejects the transaction proposal. If approved, the order will be sent to the simulated exchange and executed.

<p align="center">
  <img src="assets/risk.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

## Installation and CLI

### Installation

Clone TradingAgents:
```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

TradingAgents needs Python 3.11 or later. Create a virtual environment in any of your favorite environment managers:
```bash
conda create -n tradingagents python=3.13
conda activate tradingagents
```

Or with [uv](https://docs.astral.sh/uv/):
```bash
uv venv --python 3.13
source .venv/bin/activate
```

Install the package and its dependencies (`uv pip install .` with uv):
```bash
pip install .
```

For Toss Securities read-only portfolio summaries and synthetic demos, see [the portfolio analysis guide](docs/portfolio-analysis.md).

### Docker

Alternatively, run with Docker:
```bash
cp .env.example .env  # add your API keys
docker compose run --rm tradingagents
```

After updating the repository, rebuild the image with `docker compose build`.

Results, reports, the memory log and the cache live in the `tradingagents_data` volume. To keep them in a folder on the host instead, create the folder and point `TRADINGAGENTS_DATA_DIR` at it, in `.env` or the shell: `mkdir -p data && TRADINGAGENTS_DATA_DIR=./data docker compose run --rm tradingagents`.

For local models with Ollama:
```bash
docker compose --profile ollama run --rm tradingagents-ollama
```

### Required APIs

TradingAgents supports multiple LLM providers. Set the API key for your chosen provider:

```bash
export OPENAI_API_KEY=...          # OpenAI (GPT)
export GOOGLE_API_KEY=...          # Google (Gemini)
export ANTHROPIC_API_KEY=...       # Anthropic (Claude)
export XAI_API_KEY=...             # xAI (Grok)
export DEEPSEEK_API_KEY=...        # DeepSeek
export DASHSCOPE_API_KEY=...       # Qwen (international, dashscope-intl.aliyuncs.com)
export DASHSCOPE_CN_API_KEY=...    # Qwen (China, dashscope.aliyuncs.com)
export ZHIPU_API_KEY=...           # GLM via Z.AI (international)
export ZHIPU_CN_API_KEY=...        # GLM via BigModel (China, open.bigmodel.cn)
export MINIMAX_API_KEY=...         # MiniMax (global, api.minimax.io)
export MINIMAX_CN_API_KEY=...      # MiniMax (China, api.minimaxi.com)
export OPENROUTER_API_KEY=...      # OpenRouter
export MISTRAL_API_KEY=...         # Mistral
export MOONSHOT_API_KEY=...        # Kimi (Moonshot)
export GROQ_API_KEY=...            # Groq
export NVIDIA_API_KEY=...          # NVIDIA NIM
export FRED_API_KEY=...            # FRED macro data (free, optional)
export ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage
export TYPESAFE_API_KEY=...        # Jev social-post screening (optional)
```

For Azure OpenAI, copy `.env.enterprise.example` to `.env.enterprise` and fill in your credentials. With Docker, put these keys in `.env` instead: the image does not include `.env` files.

To run on your ChatGPT Plus or Pro plan instead of an API key, choose "Subscription" in the CLI's provider menu, or set `llm_provider: "chatgpt"`. Sign in once with `tradingagents login chatgpt`: it prints an address to open in your browser, which returns to this machine on `127.0.0.1`. When the browser runs on another machine, or TradingAgents runs in Docker (`docker compose run --rm tradingagents login chatgpt`), paste the address the browser ends up on. The sign-in is kept in `~/.tradingagents/chatgpt-auth.json`, and `tradingagents logout chatgpt` revokes it. Runs count toward your plan's usage limits, and the plan does not accept `temperature` or `max_tokens`.

For AWS Bedrock, install the extra with `pip install ".[bedrock]"`, set `llm_provider: "bedrock"`, configure AWS credentials (environment variables, `~/.aws/credentials`, or an IAM role) and `AWS_DEFAULT_REGION`, and use a Bedrock model ID, e.g. `us.anthropic.claude-opus-5-5`.

For the separate legacy `provider=openai`, `openai_auth=chatgpt_plan` path, the local open-source CLI can request ChatGPT plan usage through Sign in with ChatGPT instead of an OpenAI API key. Install the optional token-validation dependency, authorize the app in your browser, then opt in:

```bash
pip install ".[chatgpt-plan]"
tradingagents auth connect
tradingagents auth models
```

Put these settings in `.env`, replacing the model placeholders with IDs from `tradingagents auth models`:

```dotenv
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_OPENAI_AUTH=chatgpt_plan
TRADINGAGENTS_DEEP_THINK_LLM=<account-model-id>
TRADINGAGENTS_QUICK_THINK_LLM=<account-model-id>
```

The default authentication mode remains `api_key`. ChatGPT plan mode does not read `OPENAI_API_KEY`, does not fall back to API-key billing, and uses streamed Responses API requests with storage disabled and no automatic retries. Eligible plan usage is shared across apps, and account usage credits may also apply; check ChatGPT Settings → Usage for current limits, credits, and app access. Account/workspace eligibility and available models can vary. Manage the local connection with `tradingagents auth status` and `tradingagents auth disconnect`.

For local models, configure Ollama with `llm_provider: "ollama"`. The default endpoint is `http://localhost:11434/v1`; set `OLLAMA_BASE_URL` to point at a remote `ollama-serve`. Pull models with `ollama pull <name>`, and pick "Custom model ID" in the CLI for any model not listed by default.

For any other OpenAI-compatible server (vLLM, LM Studio, llama.cpp, or a custom relay), use `llm_provider: "openai_compatible"` and set the endpoint via `backend_url` (or `TRADINGAGENTS_LLM_BACKEND_URL`), e.g. `http://localhost:8000/v1` for vLLM or `http://localhost:1234/v1` for LM Studio. The model is whatever your server serves. No key is needed for local servers; set `OPENAI_COMPATIBLE_API_KEY` when the endpoint requires one.

With `TYPESAFE_API_KEY` set, the Sentiment Analyst screens StockTwits and Reddit posts with TypeSafe's Jev before reading them. Posts that are not about the company are dropped, and each source opens with a count of the remaining posts by stance: bullish, bearish, neutral, or unclear. Without the key, posts pass through unscreened. `jev-latest` moves with new releases; set `TYPESAFE_DEFAULT_MODEL` to a versioned ID such as `jev-1.13.0` to hold it fixed across runs. To reach Jev through OpenRouter, put an OpenRouter key in `TYPESAFE_API_KEY` and set `TYPESAFE_BASE_URL=https://openrouter.ai/api`.

Alternatively, copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

### CLI Usage

New Codex worker sessions run `tradingagents doctor` automatically at startup after the repository hook is trusted once in Codex (`/hooks`). If a network destination fails, the hook also provides the restricted policy JSON for the Orca execution host. For a manual export, run `tradingagents network-policy --format json`. The output lists DNS resolver access and TCP destinations for the selected quick/deep LLM endpoints and configured data-provider chains, plus the directly used sentiment APIs, configured Toss/TypeSafe services, and ChatGPT plan auth when selected, without printing full URLs or credentials. Tool-level provider overrides take precedence over category settings; `default` includes all providers available to that tool. Configure those destinations and ports in the Orca execution host's network policy, then run `tradingagents doctor` inside the same worker to check the applied route. The export does not change network permissions; loopback targets are marked `loopback` and should not be added to an internet allowlist. An `unresolved` entry needs an endpoint configured before its policy can be generated. AWS credential-chain services and redirect destinations can require extra entries, noted in the export limitations.

To check API configuration from the current process, including an Orca worker, run `tradingagents doctor`. It shows environment-variable names and whether they are set, then sends unauthenticated HTTP `HEAD` requests to the selected LLM and data API hosts. It never prints credential values or reads account data. For `provider=chatgpt`, use `tradingagents login chatgpt`; only the legacy `openai_auth=chatgpt_plan` path uses `tradingagents auth connect`. Doctor checks the selected store locally without refreshing or validating tokens. Local workers should inherit the signed-in user's home (remove unnecessary home overrides), keeping their existing worktree and working directory. They reuse login across restarts and serialize refresh through the existing file lock. Separate remote hosts or containers require their own login. If a sandbox blocks the login callback, run login in a regular terminal on the same host as the same user. Configure credentials on the worker's own execution host; do not copy them into prompts or agent messages.

Launch the interactive CLI:
```bash
tradingagents          # installed command
python -m cli.main     # alternative: run directly from source
```
You will see a screen where you can select your desired tickers, analysis date, LLM provider, research depth, and more. Your previous run's answers come back as the defaults, so pressing Enter accepts them. The `TRADINGAGENTS_*` variables in `.env` still skip their step entirely.

To run without questions, for a scheduled job or a script, answer the per-run steps with flags and the rest with `TRADINGAGENTS_*` variables:
```bash
export TRADINGAGENTS_LLM_PROVIDER=openai TRADINGAGENTS_QUICK_THINK_LLM=gpt-6-luna TRADINGAGENTS_DEEP_THINK_LLM=gpt-6.1-sol
export TRADINGAGENTS_OUTPUT_LANGUAGE=English TRADINGAGENTS_MAX_DEBATE_ROUNDS=1 TRADINGAGENTS_MAX_RISK_ROUNDS=1
tradingagents --ticker NVDA --date 2026-09-23 --analysts market,news,fundamentals --save --no-show
```
Each flag skips only its own question. Run without a terminal, a missing answer stops the run before it starts and names the flag or variable to set.

Deterministic discovery can screen supplied tickers or market sections without calling an LLM:

```bash
tradingagents discover --tickers NVDA,AAPL
tradingagents discover --universe sp500,russell2000,smallcap
tradingagents discover --universe all
```

`--universe all` includes the current U.S. exchange-listed common-stock universe, Nasdaq-100, S&P 500, Russell 1000/2000, S&P MidCap 400 and S&P SmallCap 600 sections, plus large-, mid-, small- and micro-cap bands. Cap bands use Yahoo Finance's current market-cap snapshot and project-defined thresholds: $10B+, $2B–$10B, $300M–$2B and below $300M. OTC securities are outside the listing universe. Nasdaq Trader files exclude ETFs, test issues and explicitly identified non-common securities; other listing types may still require review.

Index membership sources appear in the output. The public S&P and Russell 1000 lists are secondary sources; Russell 2000 uses iShares IWM holdings as a proxy and can differ from official membership. The screen computes the existing value, growth, quality and momentum signals once per unique ticker, shows up to 10 Bullish names per factor and section in factor-score order, and creates no cross-factor rank or investment recommendation. A first whole-market run can take a long time because it retrieves price history and SEC facts for each symbol. Select up to 10 candidates and run the regular `tradingagents --ticker <T> --date <YYYY-MM-DD>` workflow separately for deeper analysis.

At start-up the interactive CLI mentions a newer release and notices from Tauric Research. It checks at most once a day, in the background, and sends nothing about your runs; set `TRADINGAGENTS_NO_UPDATE_CHECK=1` to turn it off. Runs without a terminal never check.

A saved report also includes `complete_report.html`, the report as one page with its sections listed beside the text, for reading in a browser, on a phone or in print. Answering the save question at the prompt also asks about the page and can open it in your browser; `--no-html` skips it, and so does `ta.save_reports(state, "NVDA", html=False)` from Python.

### Markets and tickers

TradingAgents works with any market Yahoo Finance covers, using the exchange-suffixed ticker. Company identity and the alpha benchmark resolve automatically per market.

- US: `AAPL`, `SPY`
- Hong Kong: `0700.HK` · Tokyo: `7203.T` · London: `AZN.L`
- India: `RELIANCE.NS`, `.BO` · Canada: `.TO` · Australia: `.AX`
- China A-shares: Shanghai `.SS`, Shenzhen `.SZ` (e.g. `600519.SS` for Kweichow Moutai)
- Crypto: `BTC-USD`, `ETH-USD`

<p align="center">
  <img src="assets/cli/cli_init.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

An interface will appear showing results as they load, letting you track the agent's progress as it runs.

<p align="center">
  <img src="assets/cli/cli_news.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

<p align="center">
  <img src="assets/cli/cli_transaction.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

## TradingAgents Package

### Implementation Details

We built TradingAgents with LangGraph to ensure flexibility and modularity. The framework supports multiple LLM providers: OpenAI, Google, Anthropic, xAI, DeepSeek, Qwen (Alibaba DashScope, international and China endpoints), GLM (Zhipu), MiniMax (global + China), OpenRouter, Ollama for local models, Azure OpenAI for enterprise, and your own ChatGPT plan.

### Python Usage

To use TradingAgents inside your code, you can import the `tradingagents` module and initialize a `TradingAgentsGraph()` object. The `.propagate()` function will return a decision. You can run `main.py`, here's also a quick example:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# forward propagate
state, decision = ta.propagate("NVDA", "2026-09-01")
print(decision)

# the same report tree the CLI saves, under results_dir/reports
ta.save_reports(state, "NVDA")
```

You can also adjust the default configuration to set your own choice of LLMs, debate rounds, etc.

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"        # e.g. openai, google, anthropic, deepseek, groq, ollama; openai_compatible covers any OpenAI-compatible endpoint (vLLM, LM Studio, llama.cpp, ...)
config["deep_think_llm"] = "gpt-6.1-sol"  # Model for complex reasoning
config["quick_think_llm"] = "gpt-6-luna"  # Model for quick tasks
config["max_debate_rounds"] = 2

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-09-01")
print(decision)
```

The quick model serves the analysts, researchers, debaters and trader; the deep model serves the research and portfolio managers. Each can run on its own provider, for example the managers on Claude while the rest run on OpenAI:

```python
config["deep_think_provider"] = "anthropic"
config["deep_think_llm"] = "claude-opus-5-5"
```

A tier on its own provider uses that provider's key and default endpoint; set `quick_think_backend_url` or `deep_think_backend_url` for a local or relay endpoint. The `TRADINGAGENTS_DEEP_THINK_PROVIDER` and `TRADINGAGENTS_QUICK_THINK_PROVIDER` variables set them for the CLI, together with the tier's model variable.

See `tradingagents/default_config.py` for all configuration options.

### Fundamentals as filed

US company statements come from SEC EDGAR, which records the date every figure was filed. A run dated in the past reads the statements exactly as they stood that day: a fiscal year that has ended but has not been filed yet is not served, and a figure restated later still reads as first reported. Apple's 2008 total assets were filed as $39.6B and restated to $36.2B in 2010, so a run dated in between reads $39.6B. EDGAR needs no account or API key.

Other companies' statements come from Yahoo Finance, which dates a statement by the period it covers rather than by when it was published. A run dated today reads them; a run dated in the past is told they are withheld, since Yahoo cannot say which figures were public by then.

Insider trades are dated by when they happened, not when they were filed, so a run dated in the past is told they are withheld as well.

SEC asks callers to identify themselves and refuses requests that carry no contact address, so a default one is sent. Set your own so SEC can reach you rather than the project:

```bash
SEC_EDGAR_USER_AGENT="Your Name your@email.com"
```

It covers companies that file with the SEC, including foreign companies listed in the US. Anything else, such as Hong Kong or A-share listings, falls through to the next vendor in the chain. EDGAR's machine-readable filings begin in 2009, and a fourth quarter is reported as unavailable rather than derived, because filers publish it only inside the annual figure.

### Current holdings

By default the agents do not know what you hold, so their guidance is written for a reader who applies it to their own position. Pass a portfolio to have the trader, the risk analysts and the portfolio manager work against your actual book.

```python
from tradingagents.portfolio import PortfolioContext

portfolio = PortfolioContext.model_validate({
    "cash": 25000.0,
    "currency": "USD",
    "positions": [{"ticker": "NVDA", "quantity": 120, "average_price": 150.0}],
})
_, decision = ta.propagate("NVDA", "2026-09-01", portfolio=portfolio)
```

The CLI takes the same content as a JSON file: `tradingagents --portfolio my_book.json`.

An empty `positions` list means a flat book, which is different from passing nothing. A run without a portfolio is never treated as flat.

## Persistence and Recovery

TradingAgents persists two kinds of state across runs.

### Memory log

The memory log is always on. Each completed run appends its decision to `~/.tradingagents/memory/trading_memory.md`. While the analysts of a later run work, TradingAgents settles every logged decision whose holding period has passed: it fetches the realised return (raw, and alpha against the instrument's regional benchmark) and generates a one-paragraph reflection. The Portfolio Manager then reads the most recent decisions for the same ticker plus recent lessons from other tickers, so each analysis carries forward what worked and what didn't. If settling fails, the run goes on and its report says so.

Override the path with `TRADINGAGENTS_MEMORY_LOG_PATH`.

To settle decisions without running an analysis, for a scheduled job, call `ta.settle_all_pending()`; it returns the decisions it settled and any it could not.

### Checkpoint resume

Checkpoint resume is opt-in via `--checkpoint`. When enabled, LangGraph saves state after each node so a crashed or interrupted run resumes from the last successful step instead of starting over. The run view says whether it resumed a saved run or started fresh. Checkpoints are cleared automatically on successful completion.

Per-ticker SQLite databases live at `~/.tradingagents/cache/checkpoints/<TICKER>.db` (override the base with `TRADINGAGENTS_CACHE_DIR`). Use `--clear-checkpoints` to reset all of them before a run.

```bash
tradingagents --checkpoint           # enable for this run
tradingagents --clear-checkpoints    # reset before running
```

```python
config = DEFAULT_CONFIG.copy()
config["checkpoint_enabled"] = True
ta = TradingAgentsGraph(config=config)
_, decision = ta.propagate("NVDA", "2026-09-01")
```

## Evaluating decisions over time

One run gives one decision, which cannot tell you whether the system decides well. `run_backtest` runs the same pipeline over a grid of tickers and dates, writes to a memory log of its own, and scores the decisions whose holding window has since traded.

```python
from tradingagents.backtest import iter_grid, run_backtest, summarize

dates = iter_grid("2026-06-01", "2026-08-01", every_n_days=7)
result = run_backtest(["NVDA", "AAPL"], dates, config, selected_analysts=["market", "news"])
print(summarize(result).render())
```

From the CLI:

```bash
tradingagents backtest NVDA,AAPL --start 2026-06-01 --end 2026-08-01 --every 7
```

Each cell is scored on realized alpha against the instrument's regional benchmark, grouped by rating. A decision is entered at the first close after its date, because a run reads news published after that day's close. Your own memory log is never written to, and re-running the same grid with `run_id=result.run_id` skips the cells that already ran, so an interrupted sweep continues where it stopped.

### Style scores without a model

`tradingagents.style_scores` computes value (earnings yield), growth (fiscal-year revenue growth), quality (return on equity) and momentum (12-1 month return) signals by arithmetic alone: SEC EDGAR figures as filed by the date, prices cut at the date, and the price restated in filing-day shares across later splits. A style whose inputs are missing reports `Abstain`, never `Neutral`. `style-backtest` checks whether those signals predicted alpha, each over its own horizon (252 trading days for value, growth and quality; 63 for momentum), without calling a model:

```bash
tradingagents style-backtest NVDA,AAPL,MSFT --start 2022-12-01 --end 2026-08-01 --every 30
```

A first run over 40 US large caps found no signal ordered Bullish > Neutral > Bearish (see `openspec/changes/archive/2026-11-11-style-factor-scores/README.md`). Tickers chosen today miss the names that later failed, monthly cells with year-long windows overlap, and thresholds are fixed rather than sector-relative, so treat the output as indicative.

## Reproducibility

TradingAgents is LLM-driven, so two runs of the same ticker and date can differ. This is expected for a research tool built on language models, not a defect. The variation comes from a few distinct sources, and it helps to separate them.

Language model sampling is non-deterministic. Even at a fixed temperature, providers do not guarantee byte-identical output across calls, and reasoning models (the default GPT-6 family, and any thinking-mode model) vary the most because their internal reasoning is itself sampled.

Live data moves. News, StockTwits, and Reddit return different content as time passes, so a run today sees different inputs than a run last week even for the same historical trade date. Pin the analysis date to hold the price and indicator window fixed, but the social and news sources still reflect "now".

To reduce variation you can lower the sampling temperature. Set `temperature` in your config (or `TRADINGAGENTS_TEMPERATURE` in `.env`); lower values make models that honor it more repeatable. The current curated models are reasoning-first and largely ignore temperature, so for tighter reproducibility name a non-reasoning model in your config, or in `TRADINGAGENTS_DEEP_THINK_LLM` and `TRADINGAGENTS_QUICK_THINK_LLM`. Any model ID your provider serves is accepted, whether or not the picker lists it.

```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"
config["temperature"] = 0.0
# Reasoning models ignore temperature. For tighter reproducibility, name a
# non-reasoning model in deep_think_llm / quick_think_llm.
```

What does not vary anymore: the analyzed company identity is resolved deterministically from the ticker before any agent runs, and the market analyst grounds exact price and indicator claims in a verified data snapshot. Earlier reports of "different companies" or fabricated price levels across runs are addressed by these two mechanisms.

Backtest results are not guaranteed to match any published figure. Returns depend on the model, the temperature, the date range, data quality, and the sampling above. Treat the framework as a research scaffold for studying multi-agent analysis, not as a strategy with a fixed, replicable return.

## Contributing

Contributions are welcome: bug fixes, documentation, and feature ideas; past contributions are credited per release in [`CHANGELOG.md`](CHANGELOG.md).

## Citation

Please reference our work if you find *TradingAgents* provides you with some help :)

```
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework}, 
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138}, 
}
```

### Polymarket 별칭 연결

공개 검색은 기본적으로 `cloudfront_alias` 연결을 사용합니다. 연결 방식은 네트워크별
자동 분기 없이 실행 환경의 `TRADINGAGENTS_POLYMARKET_TRANSPORT` 값으로 선택하며,
공식 경로가 필요한 경우에만 `direct`를 명시합니다.

```bash
# 공식 direct 경로가 필요한 경우에만 설정
export TRADINGAGENTS_POLYMARKET_TRANSPORT=direct
```

Python 설정에서도 `polymarket_transport`를 지정할 수 있습니다. 허용값은 위 두
가지뿐이며, 잘못된 값은 설정 오류입니다. 이 설정은 공급자 선택과 독립적입니다.
기본 예측시장 공급자는 Polymarket입니다. Kalshi를 사용하려면 기존 설정의
`data_vendors.prediction_markets = "kalshi"`를 지정하면 됩니다.

별칭은 시스템 DNS resolver가 반환한 공식 호스트의 canonical name에서 매번
확인하며, 유효한 `*.cloudfront.net` 이름만 허용합니다. 별도 서버나 로컬 프록시,
Wi-Fi별 인증서 설치는 필요 없습니다. HTTPS URL과 TLS SNI는 별칭을 사용하고
HTTP Host는 공식 Gamma API를 유지합니다. **인증서는 별칭에 대해 검증**하므로
공식 Polymarket 호스트 인증서를 검증하는 것과 보장 범위가 다릅니다. CDN·DNS
변경이나 네트워크 정책 변경으로 실패할 수 있으며 공식 경로로 자동 전환하지
않습니다. 두 모드 모두 인증서 검증을 켜고 리다이렉트를 거부하며, 요청 timeout은
30초, HTTP 시도는 최대 3회입니다.

doctor는 공식 경로와 선택된 별칭의 HEAD 도달성을 따로 표시합니다. HEAD 응답은
검색 GET 성공을 뜻하지 않으며, 별칭 성공이 공식 연결 복구를 뜻하지 않습니다.
네트워크 정책 출력에는 동적으로 확인한 별칭 목적지 또는 해결 실패가 반영됩니다.

### 미국 시장 마감·장후 보고서

```bash
tradingagents market-report
tradingagents market-report --no-llm --output-dir results/market-reports
```

동부시간 20시 이후에는 당일, 그 이전·휴장일에는 직전 완료 거래일을 선택합니다. 거래소 캘린더로 휴장·조기 폐장·서머타임을 처리합니다. 기본 명령은 기존 deep 모델로 한국어 해석을 작성하며, `--no-llm`은 모델을 호출하지 않습니다. 예약 실행과 계좌 조회는 없습니다.

각 실행을 새 폴더에 `report.md`, `report.html`, `evidence.json`으로 저장합니다. 지수·11개 업종 ETF·S&P 500 구성 표본의 시장 폭·매크로·기업 뉴스·장후·다음 거래일 일정을 포함합니다. 출처와 시각을 붙이고 자료가 부족하면 첫 화면에 **불완전 보고서**와 누락 범위를 표시합니다. HTML에는 표·목차·출처 링크가 있으며 외부 스크립트를 실행하지 않습니다.

Yahoo의 무료 공개 자료와 무료 키가 필요한 FRED를 사용합니다. 정규장 종가는 비수정, 기간 수익률과 시장 폭은 수정 종가이며 빠진 거래일을 보간하지 않습니다. FRED는 전일까지의 빈티지를 사용하고 관측 기간·빈도·단위와 미확인 발표 시각을 구분합니다. 다음 거래일 일정은 조회 당시 정보로, 과거 시점의 공지 여부를 보장하지 않습니다.

장후는 ES/NQ/YM/RTY 선물과 AAPL·MSFT·NVDA·AMZN·GOOGL·META·TSLA 표본의 20시 이전 완료된 5분 봉입니다. 전체 시장 장후 순위가 아니며 선물 기준 가격은 주식시장 폐장 시각 직전 가격으로 결제가격과 다릅니다. 실적 발표값·가이던스·정책 일정의 공개 시각을 검증하지 못하면 확인 불가로 남깁니다. LLM 실패나 근거 검사 탈락 시에도 수치·출처 보고서를 저장합니다. 검사는 사실성 보증이 아닙니다.

발굴 출력에는 출처 URL·조회 시각·구성 기준일·출처 종류와 단계별 소요 시간·호출 수가 포함됩니다. 동일 실행에서 공급자 심볼 별칭의 가격·SEC·분할 결과와 실패를 재사용하며 SEC 공통 티커 표는 한 번만 읽습니다. 기존 디스크 캐시 만료 정책은 유지합니다.
