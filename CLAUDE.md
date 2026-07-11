# CLAUDE.md — AI 에이전트 작업 가이드

KIS(한국투자증권) OpenAPI 기반 포트폴리오 분석 도구. CLI(`kis`) + MCP 서버(`kis-portfolio`) + React 대시보드.

## 명령 (kis/ 폴더에서, uv 관리)

```bash
uv run kis update [--from-date 2020-01-01 --to-date YYYY-MM-DD]  # 전체 갱신(API→ETL→지표), 수 분
uv run kis update --mock          # 가짜데이터 격리 실행(kis/_mock) — 회귀 테스트용, 실DB 안 건드림
uv run kis serve --no-browser     # 대시보드 http://127.0.0.1:8777
uv run kis status --json          # 기계용 상태(JSON) — exit 0=데이터 정상
uv run kis export holdings        # report|holdings|trades|financials → stdout JSON
uv run python mock_test.py        # 파이프라인 손계산 대조 회귀 테스트
```

MCP 도구(`.mcp.json` 자동 등록): get_summary/get_holdings/get_performance/get_closed_positions/
get_trades/get_financial_statements/query_db(read-only SQL)/update_portfolio.

## 데이터 위치 & .env

- 자격정보: **루트 `.env`** — `KIS_APP_KEY`/`KIS_SECRET_KEY`/`KIS_ACC` (`.env.example` 참고). **값을 절대 출력/로그하지 말 것.**
- DB: `kis/portfolio.db` · 리포트 JSON: `create-report/public/data/{portfolio,trades,financials}.json`
  (`KIS_DATA_DIR` 설정 시 `{dir}/portfolio.db` · `{dir}/report/`) — 전부 gitignore(개인 금융데이터)

## portfolio.db 스키마 (3계층)

- **입력(raw)**: `raw_domestic`(체결내역) · `raw_holdings`(잔고: 평단·수량) · `raw_realized`(기간 실현손익) — KIS API가 코퍼레이트 액션 반영해 계산한 **브로커 권위값**
- **파생**(etl이 재생성): `trades` · `holdings` · `realized` · `realized_events` · `holdings_changes` · `holdings_monthly`
- **캐시**(yfinance, 영속): `prices` · `fin`(재무지표) · `hist_daily` · `hist_monthly` · `splits` · `statements`(재무제표 기간누적)

## 주의사항

- KIS 토큰 발급 **1회/분 제한**(EGW00133) — update 연속 실행 금지. 토큰은 `.token.json` 캐시(23h)
- 잘못된 TR 호출은 계좌 잠금 위험 → `api_ingest.py`의 검증된 TR만 사용, 프로브-게이트 유지
- 실DB 실험 금지 — 테스트는 `--mock` 또는 `KIS_DATA_DIR` 격리 폴더로
- 재무제표는 `financials_api.py`가 yfinance에서 직접 받아 `statements` 테이블에 기간 누적(yfinance가 떨군 과거분 보존) — 이 캐시를 지우면 4년 이전 재무제표는 복구 불가
- `create-report/`는 표시 전용(계산 없음) — 지표 로직은 전부 `kis/compute.py`
- 커밋은 conventional commit + 한국어 Why/What/How 템플릿 (전역 CLAUDE.md 참조)
