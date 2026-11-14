# CLAUDE.md
A portfolio analysis tool on the Korea Investment & Securities (KIS) OpenAPI for the user's own account: the `kis` CLI, the `kis-portfolio` MCP server (registered by `.mcp.json`) and a React dashboard in `create-report/`. Stack: Python with uv in `kis/`; React + Vite in `create-report/`.
## Commands
- From `kis/`: `uv run kis update [--from-date 2020-01-01 --to-date YYYY-MM-DD]` refreshes everything (API → ETL → metrics, takes minutes); `uv run kis update --mock` runs on fake data in `kis/_mock` without touching the real DB
- `uv run kis serve --no-browser` serves the dashboard at http://127.0.0.1:8777; `uv run kis status --json` reports state (exit 0 = data sound); `uv run kis export holdings` prints report|holdings|trades|financials as JSON
- Tests: `uv run python mock_test.py` checks the pipeline against hand-computed values
## Rules
- Credentials are `KIS_APP_KEY` / `KIS_SECRET_KEY` / `KIS_ACC` in the root `.env` (`.env.example` shows the shape): never print or log their values
- The DB `kis/portfolio.db` and the report JSON `create-report/public/data/{portfolio,trades,financials}.json` (with `KIS_DATA_DIR` set, `{dir}/portfolio.db` and `{dir}/report/`) are the user's financial data and stay git-ignored
- Never experiment on the real DB: test with `--mock` or an isolated `KIS_DATA_DIR`
- A KIS token is issued at most once a minute (EGW00133) and cached 23 h in `.token.json`, so never run `update` back to back
