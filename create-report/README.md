# create-report

`data-etl` 가 산출한 `portfolio.json` 을 표시하는 **16:9 포트폴리오 리포트 대시보드** (기본통화 **USD**).
Vite + React + TS + Tailwind + Recharts. **계산은 하지 않고 표시만** 한다(지표 계산은 `data-etl/compute.py`).

## 데이터 흐름
```
data-etl/compute.py ─(portfolio.db + yfinance + GCP재무제표백엔드)→
   {portfolio,trades}.json + financials.json → React 렌더(16:9)
```
> JSON 은 앱 실행 시 `%APPDATA%\KIS-Report\report\` 에, 개발 시 `public/data/` 에 생성된다.
> `financials.json`(재무제표)은 용량이 커서 별도 파일로 분리해 **재무제표 탭에서 lazy fetch** 한다.

## 실행
```bash
npm ci && npm run dev           # (build / preview) — JSON 은 data-etl/compute.py 가 먼저 생성
```

## 구조 (섹션 세로 스택, 상단 탭으로 이동)
### 0. 요약 (Overview)
총 평가액·**총 손익(실현+미실현)**·전기간 IRR·누적 TWR(vs S&P500 초과%p) + **한 줄 평가**(자동) + 미니 누적곡선 + **수익 주역(종목 기여도)**.

### A. 포트폴리오 분석 (open = 현재 보유)
보유표(수량·평단·현재가·평가액·미실현·**β·PER·섹터**) + **포폴 가중평균**(β/PER/PBR/배당) + **섹터 틸트**(포폴 vs S&P500 오버/언더).

### A2. 재무제표 (재무제표 탭)
보유종목별 **손익계산서·재무상태표·현금흐름표**(연간/분기 토글). `financials.json` lazy fetch, 데이터 출처는 GCP 재무제표 백엔드(Firestore 누적). KR/US 만.

### B. 운용성과 분석 (open+closed = 계좌 전체) — 상단 3개 서브탭
- **수익률 비교**: 전기간 **IRR**·누적 **TWR**(주별) vs **S&P500·ACWI**, **지수/금액 토글**(금액=보유 평가액 $ 추이) + 연도별 막대 + **연도별 승패**.
- **운용력 평가**(일별 수익률 기준, 운용력+리스크+스타일 통합):
  - 운용력: 상승/하락 포착·**IR**·α/β·샤프·소르티노·일별 승률
  - 리스크: MDD·변동성·연속·**최고/최악의 날·달**
  - **🔑 스타일조정 알파**: 초과수익을 [시장(SPY)+성장팩터(QQQ−SPY)] 회귀 → 스타일 제거 후 잔차 알파(=실력)
  - **종목별 기여도**(실현+미실현) · **섹터 틸트**(포폴 vs S&P500 근사비중)
- **청산 포지션**(closed): 실현손익·승률·평균이익/손실·**손익비** + 종목별 번 금액·보유기간.

> **Open/Closed 분류**: 베타·섹터·가중평균=open / 실현손익·승률·손익비=closed / TWR·IRR·샤프·포착률·MDD=계좌전체(둘다).

## 지표 방법론
- 기본통화 **USD**. 해외 거래는 원래 USD(환산 불필요), **KR/CN은 거래시점 환율**(`KRW=X`·`CNY=X` 일봉 `prices.db` 캐시, 날짜별 forward-fill)로 환산.
- **TWR**: 일별 Modified Dietz, 휴장일 현금흐름은 다음 거래일로 버킷팅, 가격 forward-fill. 벤치마크 동일시점 리베이스.
  **가격 커버리지 높은 최근 구간만**(초기 레버리지/상폐 ETF는 과거가 재구성 불가 → 제외, 헤더 표기).
- **IRR**: 전기간 자금가중(현금흐름+현재평가액, 과거가 불필요).
- 벤치마크: **S&P500=`^GSPC` 지수**, **ACWI=ETF**. 둘 다 가격수익 기준.

## 시장데이터 (portfolio.db 캐시, data-etl/market.py)
`prices`(현재가/환율) · `fin`(베타·PER·PBR·배당·섹터·시총) · `hist_monthly`·`hist_daily`(과거가) · `splits`(분할).
없으면 yfinance fetch 후 저장. 미지원/상폐 종목은 직접 INSERT 가능.

## 데이터 갱신
`data-etl`: `api_ingest.py`(KIS OpenAPI) → `etl.py` → `compute.py` → `{portfolio,trades}.json`.
앱의 **[↻ 데이터 최신화]** 가 이 플로우를 실행한다. `public/data/*.json`·`portfolio.db`·`_shots` 는 개인정보/캐시라 gitignore.
