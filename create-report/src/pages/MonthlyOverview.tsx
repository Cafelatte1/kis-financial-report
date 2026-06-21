import { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceLine,
} from "recharts";
import { Card, Kpi, SectionTitle } from "../components/Kpi";
import { usd, usdShort, pct, num, pnlColor, signedShort } from "../lib/format";
import type { Report } from "../types";

const tip = { background: "#0b0f1a", border: "1px solid #1e293b", borderRadius: 8, fontSize: 12 };
const ymLabel = (ym: string) => `${ym.slice(0, 4)}년 ${Number(ym.slice(5, 7))}월`;

export default function MonthlyOverview({ r }: { r: Report }) {
  const months = r.monthly;
  const [sel, setSel] = useState(months.length ? months[months.length - 1].month : "");
  if (!months.length) return <div className="flex h-full items-center justify-center text-slate-500">월별 데이터 없음</div>;

  const idx = Math.max(0, months.findIndex((x) => x.month === sel));
  const m = months[idx];
  const recent = months.slice(Math.max(0, idx - 11), idx + 1);

  return (
    <div className="flex flex-col px-12 py-6">
      <div className="flex items-end justify-between">
        <SectionTitle kicker="Monthly Report" title={`월별 개요 — ${ymLabel(m.month)}`} />
        <div className="flex items-center gap-2 text-[11px] text-slate-500">
          <span>조회 월</span>
          <select value={sel} onChange={(e) => setSel(e.target.value)}
            className="rounded-md border border-white/10 bg-[#151b2e] px-2 py-1 text-xs text-slate-200 outline-none">
            {[...months].reverse().map((x) => (
              <option key={x.month} value={x.month}>{ymLabel(x.month)}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <Kpi label="월말 평가액" value={usdShort(m.value)} sub={`전월대비 ${signedShort(m.value_chg)}`} />
        <Kpi label="이달 수익률" accent={pnlColor(m.port_ret)} value={pct(m.port_ret)}
          sub={`S&P500 ${pct(m.SP500_ret)}`} />
        <Kpi label="이달 실현손익" accent={pnlColor(m.realized)} value={usdShort(m.realized)} />
        <Kpi label="이달 매매" value={`${m.n_trades}건`} sub={`매수 ${usdShort(m.buy)} · 매도 ${usdShort(m.sell)}`} />
      </div>

      <div className="mt-3 flex h-[46vh] gap-3">
        <Card className="flex flex-1 flex-col">
          <div className="mb-1 text-sm font-medium text-slate-300">최근 12개월 수익률 (%) — 포폴 vs 벤치마크</div>
          <div className="min-h-0 flex-1">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={recent} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="month" stroke="#64748b" fontSize={10} tickFormatter={(v) => v.slice(2)} />
                <YAxis stroke="#64748b" fontSize={10} width={32} />
                <Tooltip contentStyle={tip} formatter={(v: unknown, n) => [`${num(Number(v), 1)}%`, n as string]} />
                <Legend wrapperStyle={{ fontSize: 11 }} /><ReferenceLine y={0} stroke="#475569" />
                <Bar name="포폴" dataKey="port_ret" fill="#818cf8" radius={[2, 2, 0, 0]} />
                <Bar name="S&P500" dataKey="SP500_ret" fill="#22c55e" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <div className="flex w-[34%] flex-col gap-3">
          <Card className="flex-1">
            <div className="mb-1 text-sm font-medium text-emerald-300">＋ 신규/재진입</div>
            <div className="flex flex-wrap gap-1.5">
              {m.new.length ? m.new.map((x) => (
                <span key={x.symbol} className="rounded-md bg-emerald-500/15 px-2 py-1 text-[11px] text-emerald-300">
                  {x.symbol} <span className="text-emerald-200/60">{x.name}</span>
                </span>
              )) : <span className="text-xs text-slate-600">없음</span>}
            </div>
          </Card>
          <Card className="flex-1">
            <div className="mb-1 text-sm font-medium text-rose-300">－ 청산</div>
            <div className="flex flex-wrap gap-1.5">
              {m.closed.length ? m.closed.map((x) => (
                <span key={x.symbol} className="rounded-md bg-rose-500/15 px-2 py-1 text-[11px] text-rose-300">
                  {x.symbol} <span className="text-rose-200/60">{x.name}</span>
                </span>
              )) : <span className="text-xs text-slate-600">없음</span>}
            </div>
          </Card>
          <Card>
            <div className="text-[11px] leading-relaxed text-slate-400">
              {ymLabel(m.month)} 포폴 <b className={pnlColor(m.port_ret)}>{pct(m.port_ret)}</b>,
              S&P500 대비 <b className={pnlColor((m.port_ret ?? 0) - (m.SP500_ret ?? 0))}>
                {pct((m.port_ret ?? 0) - (m.SP500_ret ?? 0))}p</b>,
              실현손익 <b className={pnlColor(m.realized)}>{usd(m.realized)}</b>.
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
