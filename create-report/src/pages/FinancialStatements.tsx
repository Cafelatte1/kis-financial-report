import { useEffect, useMemo, useState } from "react";
import { Card, SectionTitle } from "../components/Kpi";
import type { Financials, Statement, StatementSet } from "../types";

type Freq = "annual" | "quarterly";
const STMTS: { key: "income" | "balance" | "cashflow"; label: string }[] = [
  { key: "income", label: "손익계산서" },
  { key: "balance", label: "재무상태표" },
  { key: "cashflow", label: "현금흐름표" },
];

function fmt(v: number | string | undefined): string {
  if (v == null) return "—";
  if (typeof v === "string") return v;
  if (!isFinite(v)) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e12) return sign + (a / 1e12).toFixed(2) + "T";
  if (a >= 1e9) return sign + (a / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return sign + (a / 1e6).toFixed(1) + "M";
  if (a >= 1e3) return sign + (a / 1e3).toFixed(0) + "K";
  return String(v);
}

// 기간 내림차순(최신 좌측), 라인항목은 최신기간 순서 우선 + 과거에만 있는 항목 보충
function periodsOf(s: Statement): string[] {
  return Object.keys(s).sort().reverse();
}
function itemsOf(s: Statement, periods: string[]): string[] {
  const seen = new Set<string>(), order: string[] = [];
  for (const p of periods) for (const k of Object.keys(s[p] || {})) if (!seen.has(k)) { seen.add(k); order.push(k); }
  return order;
}

function StatementTable({ s }: { s: Statement }) {
  const periods = periodsOf(s);
  const items = itemsOf(s, periods);
  if (!periods.length || !items.length)
    return <div className="px-1 py-2 text-[11px] text-slate-500">데이터 없음</div>;
  return (
    <table className="w-full text-[11px] tabular-nums">
      <thead>
        <tr className="text-slate-400">
          <th className="sticky left-0 z-10 bg-[#151b2e] py-1 text-left font-medium">항목</th>
          {periods.map((p) => <th key={p} className="py-1 px-2 text-right font-medium">{p}</th>)}
        </tr>
      </thead>
      <tbody>
        {items.map((it) => (
          <tr key={it} className="border-t border-white/5">
            <td className="sticky left-0 z-10 bg-[#151b2e] py-[3px] pr-3 text-left text-slate-300">{it}</td>
            {periods.map((p) => <td key={p} className="py-[3px] px-2 text-right text-slate-400">{fmt(s[p]?.[it])}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function FinancialStatements() {
  const [data, setData] = useState<Financials | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sym, setSym] = useState("");
  const [freq, setFreq] = useState<Freq>("annual");

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/financials.json`)
      .then((res) => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.json(); })
      .then((d: Financials) => { setData(d); const ks = Object.keys(d); if (ks.length) setSym(ks[0]); })
      .catch((e) => setErr(String(e)));
  }, []);

  const symbols = useMemo(() => (data ? Object.keys(data) : []), [data]);
  const entry = data && sym ? data[sym] : null;
  const set: StatementSet | null = entry ? entry[freq] : null;
  const ccy = entry?.country === "KR" ? "KRW" : entry?.country === "US" ? "USD" : "현지통화";

  if (err || (data && !symbols.length))
    return (
      <div className="px-12 py-6">
        <SectionTitle title="재무제표" />
        <Card className="mt-2 text-[12px] text-slate-400">
          재무제표 데이터가 없습니다. KIS 앱에서 <b>[데이터 최신화]</b>로 생성됩니다
          (커버 국가: 미국·한국 보유 종목).
        </Card>
      </div>
    );
  if (!data) return <div className="px-12 py-6 text-[12px] text-slate-500">불러오는 중…</div>;

  return (
    <div className="flex flex-col px-12 py-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SectionTitle title="재무제표" />
        <div className="flex items-center gap-3">
          <span className="text-[11px] text-slate-500">단위 {ccy} · T=조 B=10억 M=백만 · 출처 yfinance(GCP 캐시)</span>
          <select
            value={sym}
            onChange={(e) => setSym(e.target.value)}
            className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-200"
          >
            {symbols.map((s) => (
              <option key={s} value={s} className="bg-[#0b0f1a]">{s} · {data[s].name}</option>
            ))}
          </select>
          <div className="flex gap-1 rounded-xl bg-white/5 p-1 text-xs">
            {(["annual", "quarterly"] as Freq[]).map((f) => (
              <button key={f} onClick={() => setFreq(f)}
                className={`rounded-lg px-3 py-1.5 transition ${freq === f ? "bg-indigo-500 text-white" : "text-slate-400 hover:text-slate-200"}`}>
                {f === "annual" ? "연간" : "분기"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {!set ? (
        <Card className="mt-2 text-[12px] text-slate-400">해당 주기({freq === "annual" ? "연간" : "분기"}) 데이터가 없습니다.</Card>
      ) : (
        <div className="mt-2 grid grid-cols-1 gap-3 xl:grid-cols-3">
          {STMTS.map((st) => (
            <Card key={st.key} className="max-h-[72vh] overflow-auto">
              <div className="mb-1 text-[12px] font-semibold text-indigo-300">{st.label}</div>
              <StatementTable s={set[st.key] || {}} />
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
