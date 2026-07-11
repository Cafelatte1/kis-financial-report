"""KIS OpenAPI → 입력 테이블 적재(스크랩 대체).

코퍼레이트 액션(분할/전환/무상/합병)을 행으로 주는 KIS API 는 없으므로,
이를 이미 반영해 '브로커가 계산한' 값을 직접 가져온다:
  - raw_domestic : 체결 매수/매도(국내 TTTC0081R/CTSC9215R + 해외 TTTS3035R) → trades·TWR
  - raw_holdings : 현재 보유(국내 TTTC8434R + 해외 CTRP6504R) — 수량·매입원가·평단(코퍼액션 반영)
  - raw_realized : 종목별 실현손익(국내 TTTC8715R + 해외 TTTS3039R) — 코퍼액션 반영
etl.py 가 위 3개 입력테이블에서 파생(holdings/realized/trades…)을 생성한다.

안전: 연도 루프 전 프로브 1건(rt_cd=0) 확인. 계좌비밀번호 미사용. 시크릿 마스킹.
자격정보: env(KIS_APP_KEY/KIS_SECRET_KEY/KIS_ACC) 우선, 없으면 루트 .env 로드.
"""
import os
import re
import json
import time
import datetime
import collections

import requests

import db

BASE = "https://openapi.koreainvestment.com:9443"
DOM_CCLD = f"{BASE}/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
OVS_CCLD = f"{BASE}/uapi/overseas-stock/v1/trading/inquire-ccnl"
DOM_BAL = f"{BASE}/uapi/domestic-stock/v1/trading/inquire-balance"
OVS_BAL = f"{BASE}/uapi/overseas-stock/v1/trading/inquire-present-balance"
DOM_PROFIT = f"{BASE}/uapi/domestic-stock/v1/trading/inquire-period-trade-profit"
OVS_PROFIT = f"{BASE}/uapi/overseas-stock/v1/trading/inquire-period-profit"

# raw_domestic 정규 컬럼(스크랩과 동일 스키마). 미사용 컬럼은 빈값.
RAW_COLS = ["계좌", "조회구간", "거래일", "거래종류", "종목번호", "종목명", "상품유형",
            "거래수량", "거래단가", "환율", "거래통화", "거래금액", "정산금액", "수수료",
            "거래세", "세금", "부가세", "유가잔고", "외화잔액", "잔액", "잔고번호", "접속매체"]
HOLD_COLS = ["symbol", "name", "currency", "country", "quantity", "cost_basis", "avg_cost"]
REAL_COLS = ["date", "symbol", "name", "currency", "country", "sold_qty", "proceeds", "cost", "pnl"]

# 해외 거래소코드 → 통화(분석대상은 US=USD; 그 외는 raw 보존·통계제외)
EXG_CCY = {"NASD": "USD", "NAS": "USD", "NYSE": "USD", "NYS": "USD", "AMEX": "USD", "AMS": "USD",
           "SEHK": "HKD", "HKS": "HKD", "SHAA": "CNY", "SZAA": "CNY", "SHS": "CNY", "SZS": "CNY",
           "TKSE": "JPY", "TSE": "JPY", "HASE": "VND", "VNSE": "VND"}


def _country(cur):
    return "KR" if cur in ("", "KRW") else {"USD": "US", "CNY": "CN", "JPY": "JP", "HKD": "HK"}.get(cur)


def _num(x):
    return float(str(x or "0").replace(",", "") or 0)


def _iso(d):
    """YYYYMMDD → YYYY-MM-DD (transform.iso_date 가 ISO 그대로 통과시키도록)."""
    d = (d or "").strip()
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 and d.isdigit() else d


def _load_creds():
    """이미 설정된 env 우선, 없으면 루트 .env 를 로드해 채운다(override=False)."""
    try:
        from dotenv import load_dotenv
        root_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        load_dotenv(root_env, override=False)
    except ImportError:
        pass
    appkey = os.environ.get("KIS_APP_KEY")
    secret = os.environ.get("KIS_SECRET_KEY")
    acc = os.environ.get("KIS_ACC")
    if not (appkey and secret and acc):
        raise SystemExit("ERROR: missing credentials - set KIS_APP_KEY/KIS_SECRET_KEY/KIS_ACC in .env (see .env.example)")
    digits = re.sub(r"\D", "", acc)
    return appkey, secret, digits[:8], (digits[8:10] or "01")


APPKEY, SECRET, CANO, ACNT_PRDT_CD = _load_creds()
TOKEN_CACHE = os.path.join(os.path.dirname(db.DB_PATH), ".token.json")


def get_token():
    if os.path.exists(TOKEN_CACHE):
        try:
            c = json.load(open(TOKEN_CACHE))
            if c.get("expire", 0) > time.time() + 60:
                return c["token"]
        except (json.JSONDecodeError, OSError):
            pass
    r = requests.post(f"{BASE}/oauth2/tokenP", json={
        "grant_type": "client_credentials", "appkey": APPKEY, "appsecret": SECRET})
    try:
        d = r.json()
    except ValueError:
        d = {}
    tok = d.get("access_token")
    if not tok:                                        # surface KIS error body
        code = d.get("error_code") or d.get("msg_cd") or ""
        desc = d.get("error_description") or d.get("msg1") or (r.text or "")[:160]
        hint = " [rate limit: retry in 1 min]" if "EGW00133" in code \
            else " [check APP_KEY/APP_SECRET in Settings]" if r.status_code == 403 else ""
        raise SystemExit(f"ERROR: token request failed - HTTP {r.status_code} {code}: {desc}{hint}")
    try:
        json.dump({"token": tok, "expire": time.time() + 23 * 3600}, open(TOKEN_CACHE, "w"))
    except OSError:
        pass
    return tok


TOKEN = get_token()
H = {"content-type": "application/json", "authorization": f"Bearer {TOKEN}",
     "appkey": APPKEY, "appsecret": SECRET, "custtype": "P"}


def paginate(url, tr, base_params, fk, nk, out_key, max_pages=80):
    """연속조회 전체 수집. return (rows, msg). rt_cd!=0 이면 즉시 중단."""
    rows, f, n, cont = [], "", "", ""
    for _ in range(max_pages):
        p = dict(base_params); p[fk] = f; p[nk] = n
        r = requests.get(url, headers={**H, "tr_id": tr, "tr_cont": cont}, params=p)
        d = r.json()
        if d.get("rt_cd") != "0":
            return rows, f"{d.get('msg_cd')} {d.get('msg1', '').strip()}"
        rows += d.get(out_key) or []
        if r.headers.get("tr_cont", "") in ("F", "M"):
            cont = "N"; f = (d.get(fk.lower()) or "").strip(); n = (d.get(nk.lower()) or "").strip()
            time.sleep(0.3)
        else:
            break
    return rows, "OK"


def _kr_code(pdno):
    return "00000A" + re.sub(r"\D", "", pdno or "").zfill(6)


# ----------------------------------------------------------------- 1) 체결(매수/매도)
def _dom_ccld(s, e, tr):
    p = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "INQR_STRT_DT": s, "INQR_END_DT": e,
         "SLL_BUY_DVSN_CD": "00", "PDNO": "", "CCLD_DVSN": "01", "INQR_DVSN": "01",
         "INQR_DVSN_3": "00", "ORD_GNO_BRNO": "", "ODNO": "", "INQR_DVSN_1": "", "EXCG_ID_DVSN_CD": "KRX"}
    return paginate(DOM_CCLD, tr, p, "CTX_AREA_FK100", "CTX_AREA_NK100", "output1")


def _ovs_ccld(s, e):
    p = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "PDNO": "%", "ORD_STRT_DT": s, "ORD_END_DT": e,
         "SLL_BUY_DVSN": "00", "CCLD_NCCS_DVSN": "01", "OVRS_EXCG_CD": "%", "SORT_SQN": "DS",
         "ORD_DT": "", "ORD_GNO_BRNO": "", "ODNO": ""}
    return paginate(OVS_CCLD, "TTTS3035R", p, "CTX_AREA_FK200", "CTX_AREA_NK200", "output")


def _dom_trade_row(x):
    nm = x.get("sll_buy_dvsn_cd_name", ""); q = str(x.get("tot_ccld_qty", "0")).replace(",", "").strip()
    if not (q and q != "0" and ("매수" in nm or "매도" in nm)):
        return None
    return {"거래일": _iso(x.get("ord_dt", "")), "거래종류": nm, "종목번호": _kr_code(x.get("pdno")),
            "종목명": x.get("prdt_name", ""), "상품유형": (x.get("prdt_type_cd") or "").strip(),
            "거래수량": q, "거래단가": x.get("avg_prvs", ""), "거래통화": "", "거래금액": x.get("tot_ccld_amt", "")}


def _ovs_trade_row(x):
    nm = x.get("sll_buy_dvsn_cd_name", ""); q = str(x.get("ft_ccld_qty", "0")).replace(",", "").strip()
    if not (q and q != "0" and ("매수" in nm or "매도" in nm)):
        return None
    return {"거래일": _iso(x.get("ord_dt", "")), "거래종류": nm, "종목번호": (x.get("pdno") or "").strip().upper(),
            "종목명": x.get("prdt_name", ""), "상품유형": (x.get("ovrs_excg_cd") or "").strip(),
            "거래수량": q, "거래단가": x.get("ft_ccld_unpr3", ""),
            "거래통화": (x.get("tr_crcy_cd") or "").strip(), "거래금액": x.get("ft_ccld_amt3", "")}


def collect_trades(start_year, end):
    today = datetime.date.today()
    cut = today - datetime.timedelta(days=88)
    pr, msg = _dom_ccld((today - datetime.timedelta(days=30)).strftime("%Y%m%d"),
                        today.strftime("%Y%m%d"), "TTTC0081R")
    if msg != "OK":
        raise SystemExit(f"ERROR: probe failed - aborting: {msg}")
    print("[probe] OK - collecting executions")
    rows = []
    for y in range(end.year, start_year - 1, -1):
        s = datetime.date(y, 1, 1); e = min(datetime.date(y, 12, 31), end)
        ss, ee = s.strftime("%Y%m%d"), e.strftime("%Y%m%d")
        dr, m1 = _dom_ccld(ss, ee, "TTTC0081R" if s >= cut else "CTSC9215R")
        if m1 != "OK":
            raise SystemExit(f"ERROR: domestic executions {y} failed: {m1}")
        nd = sum(1 for x in dr if (r := _dom_trade_row(x)) and rows.append(r) is None)
        orr, m2 = _ovs_ccld(ss, ee)
        if m2 != "OK":
            raise SystemExit(f"ERROR: overseas executions {y} failed: {m2}")
        no = sum(1 for x in orr if (r := _ovs_trade_row(x)) and rows.append(r) is None)
        print(f"  executions {y} | domestic {nd:>3} overseas {no:>3}")
        time.sleep(0.3)
    rows.sort(key=lambda r: (r["거래일"], r["종목번호"]))
    return rows


# ----------------------------------------------------------------- 2) 보유(잔고, 코퍼액션 반영)
def fetch_holdings():
    """현재 보유 → (raw_holdings 행 리스트, {종목번호: 수량} 앵커맵). 브로커 평단/원가."""
    out, qty = [], {}
    # 국내
    p = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "AFHR_FLPR_YN": "N", "OFL_YN": "",
         "INQR_DVSN": "02", "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
         "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00"}
    dr, md = paginate(DOM_BAL, "TTTC8434R", p, "CTX_AREA_FK100", "CTX_AREA_NK100", "output1")
    for x in dr:
        q = _num(x.get("hldg_qty"))
        if q <= 0:
            continue
        sym = _kr_code(x.get("pdno"))
        cost = _num(x.get("pchs_amt")) or q * _num(x.get("pchs_avg_pric"))
        out.append({"symbol": sym, "name": x.get("prdt_name", ""), "currency": "KRW", "country": "KR",
                    "quantity": q, "cost_basis": cost, "avg_cost": _num(x.get("pchs_avg_pric"))})
        qty[sym] = q
    # 해외(체결기준 통합잔고, 전시장/전통화)
    p = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "WCRC_FRCR_DVSN_CD": "02",
         "NATN_CD": "000", "TR_MKET_CD": "00", "INQR_DVSN_CD": "00"}
    orr, mo = paginate(OVS_BAL, "CTRP6504R", p, "CTX_AREA_FK200", "CTX_AREA_NK200", "output1")
    for x in orr:
        q = _num(x.get("cblc_qty13"))
        if q <= 0:
            continue
        sym = (x.get("pdno") or "").strip().upper()
        cur = (x.get("buy_crcy_cd") or "USD").strip()
        out.append({"symbol": sym, "name": x.get("prdt_name", ""), "currency": cur, "country": _country(cur),
                    "quantity": q, "cost_basis": _num(x.get("frcr_pchs_amt")), "avg_cost": _num(x.get("avg_unpr3"))})
        qty[sym] = q
    print(f"  holdings | domestic {sum(1 for h in out if h['country']=='KR')}({md}) "
          f"overseas {sum(1 for h in out if h['country']!='KR')}({mo})")
    return out, qty


# ----------------------------------------------------------------- 3) 실현손익(코퍼액션 반영)
def _dom_realized(s, e):
    p = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "SORT_DVSN": "00", "PDNO": "",
         "INQR_STRT_DT": s, "INQR_END_DT": e, "CBLC_DVSN": "00"}
    rows, m = paginate(DOM_PROFIT, "TTTC8715R", p, "CTX_AREA_FK100", "CTX_AREA_NK100", "output1")
    if m != "OK":
        raise SystemExit(f"ERROR: domestic realized P&L failed: {m}")
    out = []
    for x in rows:
        sq = _num(x.get("sll_qty"))
        if sq <= 0:
            continue
        pnl = _num(x.get("rlzt_pfls")); proceeds = _num(x.get("sll_amt"))
        out.append({"date": _iso(x.get("trad_dt", "")), "symbol": _kr_code(x.get("pdno")),
                    "name": x.get("prdt_name", ""), "currency": "KRW", "country": "KR",
                    "sold_qty": sq, "proceeds": proceeds, "cost": proceeds - pnl, "pnl": pnl})
    return out


def _ovs_realized(s, e):
    p = {"CANO": CANO, "ACNT_PRDT_CD": ACNT_PRDT_CD, "OVRS_EXCG_CD": "", "NATN_CD": "", "CRCY_CD": "",
         "PDNO": "", "INQR_STRT_DT": s, "INQR_END_DT": e, "WCRC_FRCR_DVSN_CD": "01"}
    rows, m = paginate(OVS_PROFIT, "TTTS3039R", p, "CTX_AREA_FK200", "CTX_AREA_NK200", "output1")
    if m != "OK":
        raise SystemExit(f"ERROR: overseas realized P&L failed: {m}")
    out = []
    for x in rows:
        sq = _num(x.get("slcl_qty"))
        if sq <= 0:
            continue
        cur = EXG_CCY.get((x.get("ovrs_excg_cd") or "").strip(), "USD")
        out.append({"date": _iso(x.get("trad_day", "")), "symbol": (x.get("ovrs_pdno") or "").strip().upper(),
                    "name": x.get("ovrs_item_name", ""), "currency": cur, "country": _country(cur),
                    "sold_qty": sq, "proceeds": _num(x.get("frcr_sll_amt_smtl1")),
                    "cost": _num(x.get("frcr_pchs_amt1")), "pnl": _num(x.get("ovrs_rlzt_pfls_amt"))})
    return out


def fetch_realized(start_year, end):
    """종목별 실현손익 per-row → raw_realized 행. 연단위 조회(전기간 단일조회는 누락 발생)."""
    out = []
    for y in range(end.year, start_year - 1, -1):
        s = datetime.date(y, 1, 1); e = min(datetime.date(y, 12, 31), end)
        ss, ee = s.strftime("%Y%m%d"), e.strftime("%Y%m%d")
        dr = _dom_realized(ss, ee); orr = _ovs_realized(ss, ee)
        out += dr + orr
        print(f"  realized {y} | domestic {len(dr):>3} overseas {len(orr):>3}")
        time.sleep(0.3)
    return out


# ----------------------------------------------------------------- 유가잔고 앵커(TWR용)
def anchor_balance(rows, qty_map):
    """종목별 cumsum(매수-매도) 을 거래후 유가잔고로 기록, 마지막 행은 잔고 API 수량으로 앵커."""
    by = collections.defaultdict(list)
    for r in rows:
        by[r["종목번호"]].append(r)
    for sym, srows in by.items():
        run = 0.0
        for r in srows:
            q = _num(r["거래수량"])
            run += q if "매수" in r["거래종류"] else -q
            r["유가잔고"] = f"{run:g}"
        srows[-1]["유가잔고"] = f"{qty_map.get(sym, 0.0):g}"
    ghost = [s for s in qty_map if s not in by]
    if ghost:
        print(f"  WARNING: {len(ghost)} held symbol(s) without execution rows:", ghost[:8])
    return rows


def main():
    print(f"[config] appkey ...{APPKEY[-4:]} | account {CANO[:4]}****-{ACNT_PRDT_CD}")
    start_year = int(os.environ.get("KIS_FROM_DATE", "2020-01-01")[:4])
    end = datetime.date.fromisoformat(os.environ["KIS_TO_DATE"]) if os.environ.get("KIS_TO_DATE") \
        else datetime.date.today()

    rows = collect_trades(start_year, end)
    holds, qty_map = fetch_holdings()
    reals = fetch_realized(start_year, end)
    rows = anchor_balance(rows, qty_map)

    meta_acc, today = f"{CANO[:4]}****-{ACNT_PRDT_CD}", datetime.date.today().isoformat()
    for r in rows:
        r["계좌"] = meta_acc; r["조회구간"] = f"~{today}"

    con = db.connect()
    db.write_raw(con, "raw_domestic", RAW_COLS, rows)
    db.write_raw(con, "raw_holdings", HOLD_COLS, holds)
    db.write_raw(con, "raw_realized", REAL_COLS, reals)
    con.close()
    kr = sum(1 for r in rows if not r["거래통화"])
    print(f"saved | raw_domestic {len(rows)} (domestic {kr}/overseas {len(rows)-kr}) "
          f"raw_holdings {len(holds)} raw_realized {len(reals)} -> {db.DB_PATH}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        print(f"ERROR: unexpected failure in api_ingest: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
