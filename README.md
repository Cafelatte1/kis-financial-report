# KIS 포트폴리오 리포트

한국투자증권(KIS) **OpenAPI**로 본인 계좌의 거래·잔고·실현손익을 수집해 **포트폴리오 분석 웹 대시보드**를 만드는 Windows 데스크톱 앱.

> ⚠️ 시작 전 **[DISCLAIMER.md](DISCLAIMER.md)** 를 반드시 읽어주세요 (비공식 도구 · 무보증 · 투자조언 아님).

## 무엇을 하나
- 앱에서 **[↻ 데이터 최신화]** → 본인 KIS 계좌를 **공식 OpenAPI로 수집→분석**, **[🌐 대시보드 열기]** → 브라우저로 **인터랙티브 웹 대시보드(보기 전용)**.
- 대시보드 구성: **월별 개요 · 요약 · 포트폴리오 분석(보유/재무지표) · 운용성과(수익률·운용력 평가·청산)**
- 현재가·재무·벤치마크는 yfinance. 자격정보(APP_KEY·APP_SECRET·계좌번호)는 **OS 자격증명 저장소(DPAPI 암호화)** 에만 저장.

## 전제조건 (사용자 PC)
- **Windows 10/11**
- **KIS 계좌**
- **[KIS Developers](https://apiportal.koreainvestment.com/)** 에서 OpenAPI 신청 → **APP_KEY / APP_SECRET** 발급(실전투자, 본인이 직접)
> 별도 브라우저·인증서·보안프로그램 설치가 필요 없습니다. 공식 OpenAPI(REST)만 사용하며, **계좌 비밀번호는 입력하지 않습니다.**

## 실행 (개발)
의존성은 폴더별 [uv](https://docs.astral.sh/uv/) 로 관리합니다.
```bash
cd create-report && npm ci && npm run build && cd ..   # 대시보드 dist
cd app && uv run python app.py                          # 앱 실행(첫 실행 시 uv 가 의존성 동기화)
```
앱에서 **⚙ 설정**에 **계좌번호 → APP_KEY → APP_SECRET** 입력 후:
- **[↻ 데이터 최신화]** — 전체 플로우(API 수집→ETL→지표계산)로 최신 데이터 생성. 진행 동안 다른 버튼은 잠깁니다.
- **[🌐 대시보드 열기]** — 생성된 데이터를 브라우저 웹 대시보드로 보기(월별 개요의 **연/월 선택 메뉴**로 과거 달도 조회). 웹은 **보기 전용**(갱신은 앱에서).

데이터·산출물은 `%APPDATA%\KIS-Report\` 아래 저장됩니다 — DB는 `portfolio.db`, 대시보드용 JSON은 `report\portfolio.json`, 로그는 `logs\app.log`.

## exe 빌드
```bash
cd app && uv run pyinstaller build.spec --noconfirm
# → app/dist/KISFinancialReport.exe
```
태그(`vX.Y.Z`) 푸시 시 **GitHub Actions** 가 Windows에서 자동 빌드 → Release 첨부.

## 코퍼레이트 액션(분할·합병·무상) 처리
- **보유수량·평단·실현손익**은 KIS가 코퍼레이트 액션을 이미 반영해 계산한 **브로커 권위값**(잔고/기간손익 API)을 사용한다 — 액면분할·종목변경·합병·무상입고가 자동 반영됨.
- **TWR 과거 수량**은 yfinance 분할정보로 보정한다(가격이 분할 소급조정되므로 수량도 현재주식수 기준으로 환산). 예: NFLX ×10, NEE ×4.
- 자세한 데이터 흐름·근거는 [`data-etl/README.md`](data-etl/README.md) 참고.

## 구조 (모노레포)
| 폴더 | 역할 |
|---|---|
| `app/` | GUI 오케스트레이터(Tkinter) + 자격정보(`kis_config`) + 빌드(spec) |
| `data-etl/` | **KIS OpenAPI 수집**(`api_ingest`) → 단일 DB(`portfolio.db`) 적재(`db`)·정규화(`etl`)·yfinance 캐시(`market`)·전 지표 계산(`compute`) → `portfolio.json` |
| `create-report/` | React 웹 대시보드 (계산 없음, `portfolio.json` 표시 전용 — 갱신 제어 없음) |
| `financials-backend/` | (Cloud Run) 재무제표 yearly/quarterly Firestore 캐시 — yfinance read-through |
| `data-pipeline/` | **(은퇴)** 구 Edge 스크래퍼 — KIS OpenAPI로 대체됨. 코드 보존용 |
| `captcha-recognizer/` | (은퇴) 구 스크래퍼용 캡차 OCR 모델 — 현재 미사용 |

단일 `portfolio.db` = 입력(raw_domestic/raw_holdings/raw_realized) + 파생(trades/holdings/realized/…) + yfinance 캐시(prices/fin/hist_*/splits).
데이터·산출물·자격정보는 모두 로컬(또는 `%APPDATA%`)에만 — 레포엔 코드만.

## 라이선스
[MIT](LICENSE) — 단, [DISCLAIMER.md](DISCLAIMER.md) 의 위험 고지에 동의하는 경우에 한함.
