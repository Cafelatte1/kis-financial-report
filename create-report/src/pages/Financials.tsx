import { Fragment } from "react";
import { Card } from "../components/Kpi";
import type { Report } from "../types";

type Fmt = "x" | "pct" | "money" | "num" | "mcap";
const GROUPS: { title: string; items: { k: string; label: string; fmt: Fmt }[] }[] = [
  { title: "밸류에이션", items: [
    { k: "pe", label: "PER", fmt: "x" }, { k: "forward_pe", label: "선행 PER", fmt: "x" }, { k: "peg", label: "PEG", fmt: "x" },
    { k: "pb", label: "PBR", fmt: "x" }, { k: "ps", label: "PSR", fmt: "x" }, { k: "ev_ebitda", label: "EV/EBITDA", fmt: "x" }] },
  { title: "수익성", items: [
    { k: "gross_margin", label: "매출총이익률", fmt: "pct" }, { k: "operating_margin", label: "영업이익률", fmt: "pct" },
    { k: "profit_margin", label: "순이익률", fmt: "pct" }, { k: "roe", label: "ROE", fmt: "pct" }, { k: "roa", label: "ROA", fmt: "pct" }] },
  { title: "성장성", items: [{ k: "rev_growth", label: "매출 성장률", fmt: "pct" }, { k: "eps_growth", label: "EPS 성장률", fmt: "pct" }] },
  { title: "재무건전성", items: [{ k: "debt_to_equity", label: "부채비율 D/E", fmt: "num" }, { k: "current_ratio", label: "유동비율", fmt: "num" }] },
  { title: "배당·기타", items: [
    { k: "div_yield", label: "배당수익률", fmt: "pct" }, { k: "payout_ratio", label: "배당성향", fmt: "pct" },
    { k: "eps", label: "EPS", fmt: "money" }, { k: "beta", label: "베타 β", fmt: "num" }, { k: "market_cap", label: "시가총액", fmt: "mcap" }] },
];

function fmt(v: unknown, f: Fmt): string {
  if (typeof v !== "number" || isNaN(v)) return "—";
  if (f === "pct") return v.toFixed(1) + "%";
  if (f === "x") return v.toFixed(1);
  if (f === "money") return "$" + v.toFixed(1);
  if (f === "num") return v.toFixed(2);
  const a = Math.abs(v);  // mcap
  if (a >= 1e12) return "$" + (v / 1e12).toFixed(2) + "T";
  if (a >= 1e9) return "$" + (v / 1e9).toFixed(0) + "B";
  return "$" + (v / 1e6).toFixed(0) + "M";
}

export default function Financials({ r }: { r: Report }) {
  const hs = r.holdings;
  return (
    <Card className="max-h-[78vh] overflow-auto">
      <div className="mb-1 text-[11px] text-slate-500">종목별 재무지표 + 포폴 가중평균(평가액 가중) · 출처 yfinance</div>
      <table className="w-full text-[11px] tabular-nums">
        <thead>
          <tr className="text-slate-400">
            <th className="sticky left-0 z-10 bg-[#151b2e] py-1 text-left font-medium">지표</th>
            <th className="py-1 pr-2 text-right font-semibold text-indigo-300">포폴평균</th>
            {hs.map((h) => <th key={h.symbol} className="py-1 text-right font-medium">{h.symbol}</th>)}
          </tr>
        </thead>
        <tbody>
          {GROUPS.map((g) => (
            <Fragment key={g.title}>
              <tr>
                <td colSpan={hs.length + 2} className="bg-white/5 px-1 py-[3px] text-[10px] font-semibold text-indigo-300">{g.title}</td>
              </tr>
              {g.items.map((it) => (
                <tr key={it.k} className="border-t border-white/5">
                  <td className="sticky left-0 z-10 bg-[#151b2e] py-[3px] text-left text-slate-300">{it.label}</td>
                  <td className="py-[3px] pr-2 text-right font-semibold text-indigo-200">
                    {it.k === "market_cap" ? "—" : fmt(r.fin_weighted[it.k], it.fmt)}
                  </td>
                  {hs.map((h) => <td key={h.symbol} className="py-[3px] text-right text-slate-400">{fmt(h.fin?.[it.k], it.fmt)}</td>)}
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
