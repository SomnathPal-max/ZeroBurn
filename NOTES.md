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
- Implemented `zeroburn.gateway.client.GatewayClient`: uses OpenAI SDK pointed at `BIFROST_URL` with virtual key headers (`Authorization: Bearer <vk>` and `x-bf-vk: <vk>`). Fully maps all HTTP error codes and body payloads.
- Implemented `zeroburn ping` CLI command testing both virtual keys and reporting serving model.

## Step 3: Policy Core (Sandbox, Repo Flag, Approval Gate, Risk Display)
- Implemented `zeroburn.policy.repo_flag`: detects confidential repositories via `.zeroburn/confidential` marker or `confidential = true` in `zeroburn.toml`.
- Implemented `zeroburn.policy.sandbox`: strictly resolves paths using `realpath`, preventing parent directory (`..`) traversal and symlink escapes outside `repo_root`. Enforces deny list blocking writes to `.git/`, `.zeroburn/`, `zeroburn.toml`, and `.env*`. Detects sensitive reads (`.env*`, `*.pem`, `id_rsa*`) requiring human confirmation.
- Implemented `zeroburn.policy.risk`: computes display-only risk scores (0-100) for all actions.
- Implemented `zeroburn.policy.approval`: `ActionKind` enum, `ActionRequest`, `Approver` protocol, `ConsoleApprover` (Rich panel with default No), and `ApprovalGate`.
- Verified with 10 unit tests in `tests/test_policy.py`.

## Step 4: Context Engine (Repo Map, Readers, Read Cache)
- Implemented `zeroburn.context.repo_map`: walks repository respecting `.gitignore` via pathspec, excluding binary and oversized (>500KB) files. Uses `tree-sitter` and `tree-sitter-python` to extract class and function signatures with line numbers (`class Name L12-58`, `def func(args) -> ret L60-88`). Prioritizes files in focus, matching task keywords, or recently touched. Enforces a strict budget ceiling (under 1500 tokens).
- Implemented `zeroburn.context.readers`: `read_range` (line-numbered, max 200 lines), `get_symbol` (AST extraction via tree-sitter), and `read_file` (size-capped at 150 lines).
- Implemented `zeroburn.context.read_cache`: tracks previously read ranges with SHA256 hashes, returning unchanged stubs for identical reads. Write operations invalidate cached entries.

## Step 5: Tool Registry
- Implemented `zeroburn.tools`:
  - Concise JSON schemas (`TOOL_SCHEMAS`) for 10 tools (`repo_map`, `search_code`, `read_range`, `get_symbol`, `read_file`, `apply_edit`, `create_file`, `run_shell`, `git`, `finish`) with descriptions under 15 words.
  - `apply_edit`: requires unique old string match; builds unified diff and requests human approval via `ApprovalGate` before modifying file.
  - `create_file`: verifies file does not exist, requests human approval, and creates file.
  - `run_shell`: executes commands only upon approval; captures stdout+stderr with timeout and character truncation.
  - `git`: all Git invocations (including status/diff) require approval and execute with `shell=False`.
  - Read tools run free for normal repository files, but prompt for human approval on sensitive files (`.env*`, `*.pem`, `id_rsa*`).
  - `ToolRegistry.execute`: formats results wrapped in `<tool_result name=...>...</tool_result>` truncated to `tool_result_max_chars`.
