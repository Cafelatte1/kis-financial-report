# data-etl

**KIS OpenAPI 수집 → 단일 SQLite(`portfolio.db`) → 전 지표 계산(`portfolio.json`)** 까지의 데이터 계층.
의존성은 [uv](https://docs.astral.sh/uv/) 로 관리(`pyproject.toml`).

## 단계
```bash
cd data-etl
uv run python api_ingest.py   # 1. KIS OpenAPI → raw 테이블(거래·잔고·실현손익)
uv run python etl.py          # 2. raw → 파생 테이블(trades/holdings/realized/…)
uv run python compute.py      # 3. 파생 + yfinance → portfolio.json / trades.json
```
> 자격정보는 환경변수(`KIS_APP_KEY`/`KIS_SECRET_KEY`/`KIS_ACC`), 조회기간은 `KIS_FROM_DATE`/`KIS_TO_DATE` 로 주입(앱이 OS 자격증명 저장소에서 읽어 전달). 출력 폴더는 `KIS_DATA_DIR`(미설정 시 로컬).

## 테이블 (단일 `portfolio.db`)
| 계층 | 테이블 | 내용 |
|---|---|---|
| 입력(raw) | `raw_domestic` | 국내·해외 **체결내역**(실행 TR) |
| 입력(raw) | `raw_holdings` | **현재 잔고**(국내 TTTC8434R + 해외 CTRP6504R) — 평단·수량 |
| 입력(raw) | `raw_realized` | **기간 실현손익**(국내 TTTC8715R + 해외 TTTS3039R) |
| 파생 | `trades` | 매수/매도, native 금액(해외=USD, KR=KRW) |
| 파생 | `holdings` | 현재 보유(브로커 잔고 권위값) |
| 파생 | `realized` | 종목별 실현손익(브로커 권위값) |
| 캐시 | `prices/fin/hist_*/splits` | yfinance 캐시(영속) |

## 정확성 설계 (핵심)
- **코퍼레이트 액션은 브로커 권위값 사용.** 액면분할·종목변경·합병·무상입고에는 별도 원장 API가 없으므로, KIS가 이미 반영해 계산한 **잔고(평단·수량)** 와 **기간 실현손익** 을 그대로 채택한다.
- **etl 경로**: raw 잔고/실현손익이 있으면 **브로커 경로**(holdings=`raw_holdings`, realized=`raw_realized` + `trades`에서 청산기간·횟수 보강). 없으면 체결내역 기반 **평균단가 엔진**으로 폴백.
- **TWR 과거 수량(compute)**: yfinance 가격이 분할 소급조정(`auto_adjust`)되므로, 과거 보유수량도 **현재주식수 기준으로 환산**한다 — 각 거래수량에 *그 거래일 이후* 분할비율을 곱하고, `현재잔고 − Σ(분할조정 전체거래)` 를 오프셋으로 더한다(`market.get_splits` 캐시). 예: NFLX ×10, NEE ×4.

## 통화
- 금액은 native 저장(해외=USD, KR=KRW). **USD 베이스 환산·전 지표 계산은 `compute.py`** 가 담당(거래시점 환율 yfinance 캐시).

## 파일
`api_ingest.py`(KIS OpenAPI 수집), `db.py`(연결·스키마 단일 권위), `etl.py`(raw→파생), `transform.py`(파싱·평균단가 엔진), `market.py`(yfinance 단일 진입점+캐시), `compute.py`(전 지표→JSON), `schema.sql`, `config.py`.

> `portfolio.db` 는 gitignore(개인 금융정보).
