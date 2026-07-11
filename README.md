# KIS Portfolio Report

한국투자증권(KIS) **OpenAPI**로 본인 계좌의 거래·잔고·실현손익을 수집해 포트폴리오를 분석하는 **개발자/AI용 CLI + MCP 도구**.
수익률(TWR/IRR)·운용력(알파/샤프/포착률)·리스크(MDD)·재무제표까지 계산해 **웹 대시보드**와 **구조화 JSON**으로 제공한다.

> ⚠️ 사용 전 **[DISCLAIMER.md](DISCLAIMER.md)** 필독 (비공식 도구 · 무보증 · 투자조언 아님).

## Quickstart

전제: [uv](https://docs.astral.sh/uv/), Node 20+, [KIS Developers](https://apiportal.koreainvestment.com/) 실전투자 APP_KEY.

```bash
git clone https://github.com/Cafelatte1/kis-financial-report && cd kis-financial-report
cp .env.example .env            # KIS_APP_KEY / KIS_SECRET_KEY / KIS_ACC 입력
cd create-report && npm ci && npm run build && cd ..   # 대시보드 빌드(1회)

cd kis
uv run kis update               # KIS OpenAPI 수집 → ETL → 지표 계산 (수 분)
uv run kis serve                # http://127.0.0.1:8777 대시보드
```

## CLI

| 명령 | 동작 |
|---|---|
| `kis update [--from-date --to-date] [--mock]` | 전체 갱신: API 수집 → ETL → 지표계산. `--mock`은 가짜데이터 격리 실행 |
| `kis serve [--port 8777] [--no-browser]` | 웹 대시보드 서빙 (보기 전용) |
| `kis status [--json]` | 데이터 존재·asof·보유종목 수 (exit 0=정상 — 스크립트/AI 판단용) |
| `kis export {report\|holdings\|trades\|financials}` | 리포트 JSON을 stdout으로 (파이프/AI용) |

데이터는 **repo 로컬**에 저장된다(전부 gitignore): DB `kis/portfolio.db`, JSON `create-report/public/data/`.
`KIS_DATA_DIR` 환경변수 또는 `--data-dir`로 위치 변경 가능.

## MCP (AI 클라이언트 연동)

루트 `.mcp.json`이 커밋되어 있어 **Claude Code에서 열면 자동 연결**된다. 다른 클라이언트(Claude Desktop 등)는:

```json
{ "mcpServers": { "kis-portfolio": {
    "command": "uv", "args": ["run", "--project", "<repo>/kis", "kis-mcp"] } } }
```

| 도구 | 내용 |
|---|---|
| `get_summary` / `get_holdings` | KPI·환율 / 보유종목(평단·평가액·재무지표) |
| `get_performance` / `get_closed_positions` | TWR·알파·샤프·MDD / 청산 포지션·승률 |
| `get_trades(symbol?, limit)` | 체결내역 조회 |
| `get_financial_statements(symbol, freq)` | 손익/재무상태/현금흐름 (annual/quarterly) |
| `query_db(sql)` | portfolio.db **read-only** 자유 질의 |
| `update_portfolio(from?, to?)` | 전체 갱신 실행 (수 분 소요) |

## 아키텍처

```
KIS OpenAPI ─→ api_ingest ─→ portfolio.db ─→ etl ─→ compute ─→ JSON 3종 ─→ React 대시보드
                                  ↑                                             (표시 전용)
                yfinance 캐시(가격·지표·분할·재무제표 누적) — 전부 로컬 SQLite
```

| 폴더 | 역할 |
|---|---|
| `kis/` | **코어** — 수집(`api_ingest`)·DB(`db`)·정규화(`etl`)·시장데이터(`market`)·전 지표(`compute`) + `cli.py`·`mcp_server.py` |
| `create-report/` | React 웹 대시보드 (계산 없음, JSON 표시 전용) |
| `data-pipeline/` | (은퇴) 구 Edge 스크래퍼 — OpenAPI로 대체, 코드 보존용 |

- **코퍼레이트 액션**(분할·합병·무상): 보유·실현손익은 KIS가 반영해 계산한 **브로커 권위값** 사용, TWR 과거수량은 yfinance 분할정보로 보정
- **재무제표**(손익/재무상태/현금흐름)는 yfinance 롤링 윈도우(~4년)를 **로컬 SQLite에 기간 누적**해 과거분 보존 — 상세는 [`kis/README.md`](kis/README.md)
- 자격정보·거래데이터는 전부 로컬(.env·db는 gitignore) — repo엔 코드만. AI 에이전트용 안내는 [`CLAUDE.md`](CLAUDE.md)

## 라이선스
[MIT](LICENSE) — 단, [DISCLAIMER.md](DISCLAIMER.md) 위험 고지에 동의하는 경우에 한함.
