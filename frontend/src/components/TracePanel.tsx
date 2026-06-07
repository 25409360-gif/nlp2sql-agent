import { CheckCircle2, Circle, Clock3, MinusCircle, XCircle } from "lucide-react";

import type { TraceEvent, TraceStatus } from "../types/trace";

const baseSteps = [
  "intent_analysis",
  "schema_retrieval",
  "schema_context_enrichment",
  "sql_generation",
  "sql_validation",
  "sql_execution",
  "sql_repair",
  "result_summary",
];

type TracePanelProps = {
  events: TraceEvent[];
  isRunning: boolean;
};

export function TracePanel({ events, isRunning }: TracePanelProps) {
  const timeline = buildTimeline(events, isRunning);

  return (
    <div className="trace-list">
      {timeline.map((event) => (
        <TraceItem event={event} key={event.step} />
      ))}
    </div>
  );
}

function TraceItem({ event }: { event: TraceEvent }) {
  return (
    <div className={`trace-item trace-item-${event.status}`}>
      <span className={`trace-dot ${event.status}`} />
      <span className="trace-icon" aria-hidden="true">
        {statusIcon(event.status)}
      </span>
      <div className="trace-body">
        <div className="trace-line">
          <span>{event.step}</span>
          <strong>{event.status}</strong>
        </div>
        <div className="trace-detail">
          <span>{traceDetail(event)}</span>
          {typeof event.duration_ms === "number" && <em>{formatDuration(event.duration_ms)}</em>}
        </div>
      </div>
    </div>
  );
}

function buildTimeline(events: TraceEvent[], isRunning: boolean): TraceEvent[] {
  const eventByStep = new Map(events.map((event) => [event.step, event]));
  const steps = Array.from(new Set([...baseSteps, ...events.map((event) => event.step)]));
  const hasEvents = events.length > 0;
  let runningAssigned = false;

  return steps.map((step) => {
    const existing = eventByStep.get(step);
    if (existing) return existing;

    const status: TraceStatus = isRunning && !runningAssigned ? "running" : "pending";
    if (status === "running") {
      runningAssigned = true;
    }

    return {
      step,
      status,
      input: {},
      output: {},
      message: hasEvents ? "Waiting for this step." : "No query has run yet.",
      duration_ms: null,
    };
  });
}

function statusIcon(status: TraceStatus) {
  if (status === "success") return <CheckCircle2 size={16} />;
  if (status === "failed") return <XCircle size={16} />;
  if (status === "skipped") return <MinusCircle size={16} />;
  if (status === "running") return <Clock3 size={16} />;
  return <Circle size={16} />;
}

function traceDetail(event: TraceEvent): string {
  const output = event.output;

  if (event.step === "intent_analysis") {
    return compact([stringValue(output.intent_type), numberPercent(output.confidence), tablesValue(output.tables)]);
  }
  if (event.step === "schema_retrieval") {
    return compact([countValue(output.matches, "matches"), tablesValue(output.tables)]);
  }
  if (event.step === "schema_context_enrichment") {
    return compact([tablesValue(output.tables)]);
  }
  if (event.step === "sql_generation") {
    return compact([stringValue(output.status), tablesValue(output.tables_used)]);
  }
  if (event.step === "sql_validation") {
    return compact([booleanValue(output.valid, "valid"), stringValue(output.error), countValue(output.limit_applied, "limit")]);
  }
  if (event.step === "sql_execution") {
    return compact([booleanValue(output.success, "success"), countValue(output.row_count, "rows"), stringValue(output.error)]);
  }
  if (event.step === "sql_repair") {
    return compact([stringValue(output.status), stringValue(output.failure_reason), arrayValue(output.attempts)]);
  }
  if (event.step === "result_summary") {
    return compact([countValue(output.row_count, "rows"), stringValue(output.source)]);
  }

  return event.message || "Waiting.";
}

function formatDuration(durationMs: number): string {
  if (durationMs >= 1000) {
    return `${(durationMs / 1000).toFixed(1)}s`;
  }
  return `${Math.round(durationMs)}ms`;
}

function compact(values: Array<string | null>): string {
  const visible = values.filter(Boolean);
  return visible.length ? visible.join(" · ") : "Waiting.";
}

function stringValue(value: unknown): string | null {
  if (typeof value !== "string" || !value) return null;
  return value;
}

function booleanValue(value: unknown, label: string): string | null {
  if (typeof value !== "boolean") return null;
  return `${label}: ${value ? "yes" : "no"}`;
}

function countValue(value: unknown, label: string): string | null {
  if (typeof value !== "number") return null;
  return `${label}: ${value}`;
}

function numberPercent(value: unknown): string | null {
  if (typeof value !== "number") return null;
  return `${Math.round(value * 100)}%`;
}

function tablesValue(value: unknown): string | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  const tableNames = value.filter((item): item is string => typeof item === "string");
  if (tableNames.length === 0) return null;
  return tableNames.slice(0, 3).join(", ");
}

function arrayValue(value: unknown): string | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  return value.filter((item): item is string => typeof item === "string").join(", ");
}
