import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine, Legend,
} from "recharts";
import { Card, Kpi, SectionTitle } from "../components/Kpi";
import { usd, usdShort, pct, num, pnlColor } from "../lib/format";
import type { Report, Contribution } from "../types";

const tip = { background: "#0b0f1a", border: "1px solid #1e293b", borderRadius: 8, fontSize: 12 };

/** 수익 주역 막대 호버: 실현/미실현 금액 + 수익률(%) 표시 */
function ContribTip({ active, payload }: { active?: boolean; payload?: { payload: Contribution }[] }) {
  if (!active || !payload?.length) return null;
  const c = payload[0].payload;
  const row = (label: string, v: number, p: number | null) => (
    <div className="flex justify-between gap-5">
      <span className="text-slate-400">{label}</span>
      <span className={`tabular-nums ${pnlColor(v)}`}>{usd(v)}{p != null ? ` (${pct(p)})` : ""}</span>
    </div>
  );
  return (
    <div className="rounded-lg border border-slate-700 bg-[#0b0f1a] px-3 py-2 text-xs">
      <div className="mb-1 font-medium text-slate-200">{c.name} <span className="text-slate-500">{c.symbol}</span></div>
      {row("실현", c.realized, c.realized_pct)}
      {row("미실현", c.unrealized, c.unrealized_pct)}
      <div className="mt-1 flex justify-between gap-5 border-t border-white/10 pt-1">
        <span className="text-slate-400">합계</span>
        <span className={`font-semibold tabular-nums ${pnlColor(c.total)}`}>{usd(c.total)}</span>
      </div>
    </div>
  );
}

export default function Overview({ r }: { r: Report }) {
  const k = r.kpi, last = r.returns.weekly.at(-1);
  const totalPnl = (k.realized_pnl ?? 0) + (k.unrealized ?? 0);
  const twrEx = last ? last.port - last.SP500 : null;
  const contrib = [...r.contributions.slice(0, 6), ...r.contributions.slice(-3)];

  return (
    <div className="flex flex-col px-12 py-6">
      <div className="flex items-end justify-between">
        <SectionTitle title="요약" />
        <div className="text-right text-[11px] text-slate-500">
          기준 {r.asof.slice(0, 16).replace("T", " ")} · USD · {k.period[0]}~{k.period[1]}
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <Kpi label="현재 평가액 (보유)" value={usdShort(k.market_value)} sub={`보유 ${k.holdings_count}종목`} />
        <Kpi label="총 손익 (실현+미실현)" accent={pnlColor(totalPnl)} value={usdShort(totalPnl)}
          sub={`실현 ${usdShort(k.realized_pnl)} · 미실현 ${usdShort(k.unrealized)}`} />
        <Kpi label="전기간 IRR (자금가중)" accent="text-amber-300" value={pct(k.irr_annual)} sub="연환산·전체기간" />
        <Kpi label="누적 TWR vs S&P500" accent="text-indigo-300" value={last ? pct(last.port - 100) : "—"}
          sub={`S&P500 ${last ? pct(last.SP500 - 100) : "—"} (초과 ${twrEx != null ? `+${twrEx.toFixed(0)}%p` : "—"})`} />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <Card>
          <div className="mb-1 text-sm font-medium text-slate-300">누적 수익률 (주별·100 기준)</div>
          <div className="h-[42vh]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={r.returns.weekly} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                <XAxis dataKey="date" stroke="#64748b" fontSize={10} minTickGap={50} />
                <YAxis stroke="#64748b" fontSize={10} width={36} />
                <Tooltip contentStyle={tip} labelStyle={{ color: "#cbd5e1" }} formatter={(v: unknown, n) => [num(Number(v), 0), n as string]} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line name="포폴" type="monotone" dataKey="port" stroke="#818cf8" strokeWidth={2} dot={false} />
                <Line name="S&P500" type="monotone" dataKey="SP500" stroke="#22c55e" strokeWidth={1.3} dot={false} />
                <Line name="ACWI" type="monotone" dataKey="ACWI" stroke="#f59e0b" strokeWidth={1.3} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card>
          <div className="mb-1 text-sm font-medium text-slate-300">수익 주역 — 종목별 기여도 (실현+미실현)</div>
          <div className="h-[42vh]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={contrib} layout="vertical" margin={{ top: 2, right: 12, left: 4, bottom: 0 }}>
                <XAxis type="number" tickFormatter={(v) => usdShort(v)} stroke="#64748b" fontSize={10} />
                <YAxis type="category" dataKey="symbol" width={48} tick={{ fill: "#cbd5e1", fontSize: 10 }} />
                <Tooltip cursor={{ fill: "#ffffff0d" }} content={<ContribTip />} />
                <ReferenceLine x={0} stroke="#475569" />
                <Bar dataKey="total" radius={[0, 3, 3, 0]}>
                  {contrib.map((c, i) => <Cell key={i} fill={(c.total ?? 0) >= 0 ? "#34d399" : "#fb7185"} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
    </div>
  );
}
