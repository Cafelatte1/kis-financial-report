import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-white/5 bg-[#151b2e] p-5 ${className}`}>
      {children}
    </div>
  );
}

export function Kpi({
  label, value, sub, accent = "text-slate-100",
}: { label: string; value: ReactNode; sub?: ReactNode; accent?: string }) {
  return (
    <Card className="flex flex-col justify-between">
      <div className="text-xs font-medium tracking-wide text-slate-400">{label}</div>
      <div className={`mt-2 text-3xl font-semibold tabular-nums ${accent}`}>{value}</div>
      {sub != null && <div className="mt-1 text-sm tabular-nums text-slate-400">{sub}</div>}
    </Card>
  );
}

export function SectionTitle({ kicker, title }: { kicker?: string; title: string }) {
  return (
    <div className="mb-4">
      {kicker && <div className="text-xs font-semibold uppercase tracking-widest text-indigo-400">{kicker}</div>}
      <h2 className="text-2xl font-bold text-slate-100">{title}</h2>
    </div>
  );
}
