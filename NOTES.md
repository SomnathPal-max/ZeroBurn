# ZeroBurn Implementation Notes

## Step 0: Project Skeleton
- Package configured with setuptools, targeting Python 3.11+.
- Virtual environment created and core dependencies installed: `openai`, `httpx`, `typer`, `rich`, `pydantic`, `tree-sitter`, `tree-sitter-python`, `pathspec`, `tavily-python`, `pyyaml`, `pytest`, `pytest-mock`.
- CLI entrypoint `zeroburn = zeroburn.cli:app` defined with 6 stubs: `run`, `stats`, `plan`, `mark-confidential`, `ping`, `init`.
- `.gitignore` configured to exclude `.env`, `.venv`, `__pycache__`, `.zeroburn/ledger.json`, `.zeroburn/usage.jsonl`.

## External API Notes: Bifrost Gateway
- Bifrost documentation verified: https://docs.getbifrost.ai
- Chat completion endpoint: `/v1/chat/completions` (OpenAI compatible).
- Base URL format: `http://localhost:8080/v1` or `http://localhost:8080`.
- Model format: `provider/model` (e.g., `ollama/llama3.1:8b`, `openai/gpt-4o-mini`).
- Virtual key header: Passed either as `Authorization: Bearer <virtual_key>` or `x-bf-vk: <virtual_key>`.
- Virtual key provider restriction: In Bifrost, virtual keys can be restricted to specific providers (e.g. `ollama` only for confidential keys). When a key is restricted, requests specifying a non-allowed provider return a 403 / 400 error indicating provider is disallowed by gateway policy.
