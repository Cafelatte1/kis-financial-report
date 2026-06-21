import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip,
} from "recharts";
import { Card } from "../../components/Kpi";
import { pct, num, pnlColor } from "../../lib/format";
import type { Report } from "../../types";

export default function Eval({ r }: { r: Report }) {
  const s = r.skill, k = r.risk, st = r.style;
  const skillReal = (st.adj_alpha_annual ?? 0) > 2;
  const radar = r.styles.map((x) => ({ style: x.key, corr: x.corr ?? 0 }));

  return (
    <div className="flex flex-col gap-2.5">
      {/* 핵심 평가 strip */}
      <div className="grid grid-cols-4 gap-2.5">
        <Mini label="연율 알파 α" value={pct(s.alpha_annual)} good={(s.alpha_annual ?? 0) > 0} desc="벤치마크 초과(연율)" />
        <Mini label="정보비율 IR" value={num(s.info_ratio)} good={(s.info_ratio ?? 0) >= 0.5} desc="꾸준히 이긴 정도" />
        <Mini label="상승/하락 포착" value={`${num(s.up_capture, 0)}/${num(s.down_capture, 0)}`} good={(s.up_capture ?? 0) > (s.down_capture ?? 0)} desc="오를 땐 더·내릴 땐 덜" />
        <Mini label="샤프" value={num(s.sharpe)} good={(s.sharpe ?? 0) >= 1} desc="위험당 수익" />
      </div>

      {/* 3열: 운용력 상세 / 리스크 / 스타일 */}
      <div className="grid grid-cols-3 gap-2.5">
        <Card>
          <div className="mb-2 text-sm font-medium text-slate-300">운용력 상세</div>
          <div className="grid grid-cols-2 gap-2">
            <Detail label="베타 β" value={num(s.beta)} />
            <Detail label="소르티노" value={num(s.sortino)} />
            <Detail label="일별 승률" value={`${num(s.win_rate, 0)}%`} />
            <Detail label="상관계수" value={num(s.corr)} />
            <Detail label="추적오차" value={`${num(s.tracking_error, 0)}%`} />
          </div>
        </Card>

        <Card>
          <div className="mb-2 text-sm font-medium text-slate-300">리스크 & 하이라이트</div>
          <div className="grid grid-cols-3 gap-2">
            <Detail label="MDD" value={pct(k.mdd)} c="text-rose-300" />
            <Detail label="변동성" value={`${num(k.vol_annual, 0)}%`} />
            <Detail label="연속↑/↓" value={`${k.max_up_streak}/${k.max_down_streak}`} />
          </div>
          <div className="mt-2 space-y-1.5 text-[11px]">
            <Hi label="최고의 날" d={k.best_day.date} v={k.best_day.ret} />
            <Hi label="최악의 날" d={k.worst_day.date} v={k.worst_day.ret} />
            <Hi label="최고의 달" d={k.best_month.month} v={k.best_month.ret} />
            <Hi label="최악의 달" d={k.worst_month.month} v={k.worst_month.ret} />
          </div>
        </Card>

        <Card className="flex flex-col">
          <div className="text-sm font-medium text-slate-300">스타일 닮은꼴 & 수익 비교</div>
          <ResponsiveContainer width="100%" height={150}>
            <RadarChart data={radar} outerRadius="68%">
              <PolarGrid stroke="#334155" />
              <PolarAngleAxis dataKey="style" tick={{ fill: "#cbd5e1", fontSize: 10 }} />
              <PolarRadiusAxis domain={[0.6, 0.85]} tick={false} axisLine={false} />
              <Radar dataKey="corr" stroke="#818cf8" fill="#818cf8" fillOpacity={0.35} />
              <Tooltip formatter={(v: unknown) => [`상관 ${num(Number(v))}`, ""]}
                contentStyle={{ background: "#0b0f1a", border: "1px solid #1e293b", borderRadius: 8, fontSize: 11 }} />
            </RadarChart>
          </ResponsiveContainer>
          <table className="w-full text-[10px] tabular-nums">
            <thead><tr className="text-slate-500">
              <th className="text-left font-medium">스타일</th><th className="text-right font-medium">상관</th>
              <th className="text-right font-medium">누적</th><th className="text-right font-medium">포폴초과</th>
            </tr></thead>
            <tbody>
              {r.styles.map((x) => (
                <tr key={x.key} className="border-t border-white/5">
                  <td className="py-0.5 text-slate-300">{x.key}</td>
                  <td className="py-0.5 text-right text-slate-400">{num(x.corr)}</td>
                  <td className="py-0.5 text-right text-slate-400">{x.cum_pct != null ? `${num(x.cum_pct, 0)}%` : "—"}</td>
                  <td className={`py-0.5 text-right ${pnlColor(x.excess_pct)}`}>{x.excess_pct != null ? `+${num(x.excess_pct, 0)}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
      <div className="text-[10px] text-slate-500">
        {skillReal ? "성장 외 스타일과도 비교 — 닮은꼴(상관) 높을수록 그 스타일과 유사. '포폴초과'는 같은 기간 누적수익률 차이(%p)." : ""}
      </div>
    </div>
  );
}

function Mini({ label, value, good, desc }: { label: string; value: string; good?: boolean; desc: string }) {
  return (
    <Card className="flex flex-col justify-center">
      <div className="flex items-center justify-between">
        <div className="text-xs text-slate-400">{label}</div>
        {good != null && <span className={`text-[10px] ${good ? "text-emerald-400" : "text-rose-400"}`}>{good ? "▲" : "▽"}</span>}
      </div>
      <div className="mt-0.5 text-xl font-semibold tabular-nums text-slate-100">{value}</div>
      <div className="text-[10px] text-slate-500">{desc}</div>
    </Card>
  );
}
function Detail({ label, value, c = "text-slate-100" }: { label: string; value: string; c?: string }) {
  return (
    <div className="rounded-lg bg-white/5 px-2 py-1.5">
      <div className="text-[10px] text-slate-500">{label}</div>
      <div className={`text-base font-semibold tabular-nums ${c}`}>{value}</div>
    </div>
  );
}
function Hi({ label, d, v }: { label: string; d: string | null; v: number | null }) {
  return (
    <div className="flex items-center justify-between border-t border-white/5 pt-1">
      <span className="text-slate-400">{label} <span className="text-slate-600">{d}</span></span>
      <span className={`font-semibold tabular-nums ${pnlColor(v)}`}>{pct(v)}</span>
    </div>
  );
}
