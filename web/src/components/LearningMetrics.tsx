import {
  Award,
  BookOpen,
  CheckCircle2,
  ChevronRight,
  Mic,
  PenLine,
  Sparkles,
  XCircle
} from "lucide-react";
import { CSSProperties } from "react";

import type { Dashboard } from "../types";

export function FunnelChart({ rows }: { rows: Array<{ label: string; value: number; tone: string }> }) {
  const max = Math.max(...rows.map((row) => row.value), 1);
  return (
    <div className="funnel-chart">
      {rows.map((row) => (
        <div className="funnel-row" key={row.label}>
          <div>
            <strong>{row.label}</strong>
            <span>{row.value}</span>
          </div>
          <i className={row.tone} style={{ "--bar": `${Math.max((row.value / max) * 100, row.value ? 6 : 0)}%` } as CSSProperties} />
        </div>
      ))}
    </div>
  );
}

export function SegmentedBar({ total, segments }: { total: number; segments: Array<{ label: string; value: number; tone: string }> }) {
  return (
    <div className="segmented-wrap">
      <div className="segmented-bar">
        {segments.map((segment) => (
          <i
            className={segment.tone}
            key={segment.label}
            style={{ "--segment": `${Math.max((segment.value / total) * 100, segment.value ? 5 : 0)}%` } as CSSProperties}
          />
        ))}
      </div>
      <div className="segment-legend">
        {segments.map((segment) => (
          <span key={segment.label}><b className={segment.tone} /> {segment.label}: {segment.value}</span>
        ))}
      </div>
    </div>
  );
}

export function MiniBars({
  rows,
  max
}: {
  rows: Array<{ label: string; value: number; tone: string; suffix?: string }>;
  max?: number;
}) {
  const ceiling = max ?? Math.max(...rows.map((row) => row.value), 1);
  return (
    <div className="mini-bars">
      {rows.map((row) => (
        <div className="mini-bar-row" key={row.label}>
          <span>{row.label}</span>
          <div><i className={row.tone} style={{ "--bar": `${Math.max((row.value / ceiling) * 100, row.value ? 6 : 0)}%` } as CSSProperties} /></div>
          <strong>{row.value}{row.suffix ?? ""}</strong>
        </div>
      ))}
    </div>
  );
}

export function MiniStat({ icon: Icon, value, label }: { icon: typeof Sparkles; value: number; label: string }) {
  return (
    <div className="mini-stat">
      <Icon size={19} />
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

export function Metric({ icon: Icon, label, value, sub }: { icon: typeof BookOpen; label: string; value: string | number; sub: string }) {
  return (
    <article className="metric-card">
      <div className="metric-icon">
        <Icon size={24} />
      </div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{sub}</small>
      </div>
    </article>
  );
}

export function GuidedEmptyState({
  icon: Icon,
  title: emptyTitle,
  text,
  actionLabel,
  onAction
}: {
  icon: typeof BookOpen;
  title: string;
  text: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <div className="guided-empty-state">
      <Icon size={26} />
      <div>
        <strong>{emptyTitle}</strong>
        <p>{text}</p>
      </div>
      <button onClick={onAction}>{actionLabel} <ChevronRight size={16} /></button>
    </div>
  );
}

export function ActivityList({ rows }: { rows: Dashboard["recent_activity"] }) {
  if (!rows.length) return <p className="muted">No activity yet.</p>;
  return (
    <div className="activity-list">
      {rows.map((row) => (
        <article key={row.id}>
          <span>{row.event_type === "dictation" ? <Mic size={16} /> : row.event_type === "achievement" ? <Award size={16} /> : <PenLine size={16} />}</span>
          <strong>{row.title}</strong>
          <small>{new Date(row.created_at).toLocaleString()}</small>
          {row.accuracy === 1 ? <CheckCircle2 size={16} /> : row.accuracy === 0 ? <XCircle size={16} /> : null}
        </article>
      ))}
    </div>
  );
}
