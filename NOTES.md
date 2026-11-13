# ZeroBurn Implementation Notes

## Step 0: Project Skeleton
- Package configured with setuptools, targeting Python 3.11+.
- Virtual environment created and core dependencies installed: `openai`, `httpx`, `typer`, `rich`, `pydantic`, `tree-sitter`, `tree-sitter-python`, `pathspec`, `tavily-python`, `pyyaml`, `pytest`, `pytest-mock`.
- CLI entrypoint `zeroburn = zeroburn.cli:app` defined with 6 stubs: `run`, `stats`, `plan`, `mark-confidential`, `ping`, `init`.
- `.gitignore` configured to exclude `.env`, `.venv`, `__pycache__`, `.zeroburn/ledger.json`, `.zeroburn/usage.jsonl`.

## Step 1: Bifrost Gateway and Ollama
- Verified endpoint path: `/v1/chat/completions` (OpenAI compatible).
- Verified headers:
  - `Authorization: Bearer <virtual_key>`
  - `x-bf-vk: <virtual_key>`
- Model-name format: `<provider>/<model>` (e.g. `openai/gpt-4o-mini`, `ollama/llama3.2:latest`, `ollama/llama3.1:8b`).
- Local model verification: Ollama running on `http://localhost:11434`, verified with `llama3.2:latest` supporting `completion` and `tools` capabilities.
- Virtual key provider restriction & error body shape:
  - Virtual keys enforce provider whitelisting (standard = cloud + Ollama, confidential = Ollama only).
  - When confidential virtual key attempts to call a cloud model (e.g. `openai/gpt-4o-mini`), Bifrost rejects the request with HTTP 403 / 400.
  - Verified error body shape for rejected requests:
    ```json
    {
      "is_bifrost_error": true,
      "status_code": 403,
      "error": {
        "message": "Virtual key sk-bf-confidential is restricted to provider [ollama]; access to provider [openai] is denied",
        "type": "gateway_policy_blocked",
        "code": "provider_disallowed"
      }
    }
    ```
- Verification scripts: `scripts/check_gateway.sh` and `scripts/check_gateway.py` implemented to run checks (a), (b), and (c).

## Step 2: Config, Errors and Gateway Client
- Implemented `zeroburn.config`: typed Pydantic models for models, budget, failover, agent, freshness, prices_usd_per_million, and context_limits. Enforces configuration precedence (`env` > repo `zeroburn.toml` > user `~/.zeroburn/zeroburn.toml` > defaults) and fails fast with a readable error message when any model is missing from `prices_usd_per_million`.
- Implemented `zeroburn.errors`: ZeroBurnError base exception and subclasses: `RateLimited`, `ProviderDown`, `BudgetBlocked`, `GatewayPolicyBlocked`, `BadRequest`, `AuthError`, `PolicyViolation`, `ApprovalDenied`, `BudgetExhausted`.
- Implemented `zeroburn.gateway.client.GatewayClient`: uses OpenAI SDK pointed at `BIFROST_URL` with virtual key headers (`Authorization: Bearer <vk>` and `x-bf-vk: <vk>`). Fully maps all HTTP error codes and body payloads:
  - 429 without budget wording -> `RateLimited`
  - 429 / 403 with budget wording -> `BudgetBlocked`
  - 403 / 400 with gateway provider refusal -> `GatewayPolicyBlocked`
  - 400 invalid schema -> `BadRequest`
  - 401 unauthorized -> `AuthError`
  - 5xx, timeouts, connection errors -> `ProviderDown`
- Implemented `zeroburn ping` CLI command testing both virtual keys and reporting serving model.
- 17 unit tests in `tests/test_client.py`, `tests/test_config.py`, and `tests/test_ping.py` cover all error mappings, config validation, and ping logic.
