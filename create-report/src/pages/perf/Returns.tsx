import { useState } from "react";
import {
  LineChart, Line, Area, AreaChart, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, ReferenceLine,
} from "recharts";
import { Card, Kpi } from "../../components/Kpi";
import { pct, num, usd, usdShort } from "../../lib/format";
import type { Report } from "../../types";

const axis = { stroke: "#64748b", fontSize: 11 };
const tip = { background: "#0b0f1a", border: "1px solid #1e293b", borderRadius: 8, fontSize: 12 };

/** 연도별 수익률 툴팁: 포폴/벤치마크 수익률 + S&P500 대비 초과(%p) */
function YearTip({ active, payload, label }: {
  active?: boolean; label?: string;
  payload?: { name: string; value: number; color: string }[];
}) {
  if (!active || !payload?.length) return null;
  const get = (n: string) => payload.find((p) => p.name === n)?.value;
  const port = get("포폴"), sp = get("S&P500");
  const excess = port != null && sp != null ? port - sp : null;
  return (
    <div className="rounded-lg border border-slate-700 bg-[#0b0f1a] px-3 py-2 text-xs">
      <div className="mb-1 font-medium text-slate-200">{label}</div>
      {payload.map((p) => (
        <div key={p.name} className="flex justify-between gap-4">
          <span style={{ color: p.color }}>{p.name}</span>
          <span className="tabular-nums text-slate-200">{num(p.value, 1)}%</span>
        </div>
      ))}
      {excess != null && (
        <div className="mt-1 flex justify-between gap-4 border-t border-white/10 pt-1">
          <span className="text-slate-400">S&amp;P500 대비</span>
          <span className={`tabular-nums ${excess >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {excess >= 0 ? "+" : ""}{excess.toFixed(1)}%p
          </span>
        </div>
      )}
    </div>
  );
}

export default function Returns({ r }: { r: Report }) {
  const [mode, setMode] = useState<"idx" | "value">("idx");
  const last = r.returns.weekly.at(-1);

  return (
    <div className="flex flex-col">
      <div className="grid grid-cols-4 gap-3">
        <Kpi label="전기간 IRR (자금가중)" accent="text-amber-300" value={pct(r.kpi.irr_annual)} sub="연환산·전체기간" />
        <Kpi label="누적 TWR (포폴)" accent="text-indigo-300" value={last ? pct(last.port - 100) : "—"}
          sub={`${r.returns.start}~${r.returns.end}`} />
        <Kpi label="누적 S&P500" value={last ? pct(last.SP500 - 100) : "—"} />
        <Kpi label="누적 ACWI" value={last ? pct(last.ACWI - 100) : "—"} />
      </div>

      <Card className="mt-3 flex h-[44vh] flex-col">
        <div className="mb-1 flex items-center justify-between">
          <div className="text-sm font-medium text-slate-300">
            {mode === "idx" ? "누적 수익률 — 포폴 vs 벤치마크 (주별·100 기준)" : "보유 평가액 추이 (주별·USD)"}
          </div>
          <div className="flex gap-1 rounded-lg bg-white/5 p-0.5 text-xs">
            {(["idx", "value"] as const).map((m) => (
              <button key={m} onClick={() => setMode(m)}
                className={`rounded-md px-2.5 py-1 ${mode === m ? "bg-indigo-500 text-white" : "text-slate-400"}`}>
                {m === "idx" ? "지수" : "금액"}
              </button>
            ))}
          </div>
        </div>
        <div className="min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          {mode === "idx" ? (
            <LineChart data={r.returns.weekly} margin={{ top: 5, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="date" {...axis} minTickGap={60} /><YAxis {...axis} width={40} />
              <Tooltip contentStyle={tip} labelStyle={{ color: "#cbd5e1" }}
                formatter={(v: unknown, n) => [num(Number(v), 0), n as string]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line name="포폴" type="monotone" dataKey="port" stroke="#818cf8" strokeWidth={2.2} dot={false} />
              <Line name="S&P500" type="monotone" dataKey="SP500" stroke="#22c55e" strokeWidth={1.5} dot={false} />
              <Line name="ACWI" type="monotone" dataKey="ACWI" stroke="#f59e0b" strokeWidth={1.5} dot={false} />
            </LineChart>
          ) : (
            <AreaChart data={r.returns.weekly} margin={{ top: 5, right: 12, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="gv" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#818cf8" stopOpacity={0.5} />
                  <stop offset="100%" stopColor="#818cf8" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="date" {...axis} minTickGap={60} />
              <YAxis {...axis} width={48} tickFormatter={(v) => usdShort(v)} />
              <Tooltip contentStyle={tip} labelStyle={{ color: "#cbd5e1" }}
                formatter={(v: unknown) => [usd(Number(v)), "보유 평가액"]} />
              <Area name="보유 평가액" type="monotone" dataKey="value" stroke="#818cf8" strokeWidth={2} fill="url(#gv)" />
            </AreaChart>
          )}
        </ResponsiveContainer>
        </div>
      </Card>

      <Card className="mt-3 flex h-[44vh] flex-col">
        <div className="mb-1 text-sm font-medium text-slate-300">연도별 수익률 (%) — 포폴 vs 벤치마크</div>
        <div className="min-h-0 flex-1">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={r.returns.yearly} margin={{ top: 5, right: 10, left: 0, bottom: 0 }} barCategoryGap="20%">
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="year" {...axis} /><YAxis {...axis} width={34} />
              <Tooltip content={<YearTip />} cursor={{ fill: "#ffffff0d" }} />
              <Legend wrapperStyle={{ fontSize: 11 }} /><ReferenceLine y={0} stroke="#475569" />
              <Bar name="포폴" dataKey="port" fill="#818cf8" radius={[2, 2, 0, 0]} />
              <Bar name="S&P500" dataKey="SP500" fill="#22c55e" radius={[2, 2, 0, 0]} />
              <Bar name="ACWI" dataKey="ACWI" fill="#f59e0b" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
}
