import { CheckCircle2, Clipboard, ClipboardCheck, Code2, MinusCircle, TriangleAlert, Wrench } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { TraceEvent, TraceStatus } from "../types/trace";

type SQLViewerProps = {
  sql: string | null;
  trace: TraceEvent[];
};

type ValidationTone = "idle" | "pending" | "running" | "success" | "failed" | "skipped";

type ValidationView = {
  label: string;
  meta: string;
  tone: ValidationTone;
  error: string | null;
  limitApplied: number | null;
  referencedTables: string[];
  safeSql: string | null;
};

export function SQLViewer({ sql, trace }: SQLViewerProps) {
  const [copied, setCopied] = useState(false);
  const validationEvent = useMemo(() => findTraceEvent(trace, "sql_validation"), [trace]);
  const repairEvent = useMemo(() => findTraceEvent(trace, "sql_repair"), [trace]);
  const validation = useMemo(() => buildValidationView(validationEvent, sql), [validationEvent, sql]);
  const displaySql = (sql || validation.safeSql || "").trim();
  const formattedSql = displaySql ? formatSql(displaySql) : "尚无 SQL";
  const repairedSql = stringOutput(repairEvent, "repaired_sql");
  const repairStatus = stringOutput(repairEvent, "status");
  const showRepair = Boolean(repairedSql && repairStatus === "repaired");

  useEffect(() => {
    setCopied(false);
  }, [displaySql]);

  async function copySql() {
    if (!displaySql) return;
    await copyText(displaySql);
    setCopied(true);
  }

  return (
    <section className="panel sql-panel sql-viewer">
      <div className="panel-title">
        <span className="panel-title-icon">
          <Code2 size={18} />
        </span>
        <span>SQL</span>
        <strong>{validation.meta}</strong>
      </div>

      <div className="sql-viewer-body">
        <div className="sql-toolbar">
          <div className="sql-status-row">
            <ValidationPill validation={validation} />
            {validation.limitApplied !== null && <span className="sql-meta-chip">LIMIT {validation.limitApplied}</span>}
            {validation.referencedTables.length > 0 && (
              <span className="sql-meta-chip">{validation.referencedTables.slice(0, 3).join(", ")}</span>
            )}
          </div>

          <button
            className="copy-button"
            disabled={!displaySql}
            title="复制 SQL"
            type="button"
            onClick={() => void copySql()}
          >
            {copied ? <ClipboardCheck size={16} /> : <Clipboard size={16} />}
            <span>{copied ? "Copied" : "Copy"}</span>
          </button>
        </div>

        <pre className={`sql-code ${displaySql ? "" : "sql-code-empty"}`}>
          <code>{formattedSql}</code>
        </pre>

        {validation.error && (
          <div className="sql-validation-message">
            <TriangleAlert size={15} />
            <span>{validation.error}</span>
          </div>
        )}

        {showRepair && repairedSql && (
          <div className="repair-section">
            <div className="repair-heading">
              <Wrench size={15} />
              <span>Repaired SQL</span>
            </div>
            <pre className="sql-code repair-code">
              <code>{formatSql(repairedSql)}</code>
            </pre>
          </div>
        )}
      </div>
    </section>
  );
}

function ValidationPill({ validation }: { validation: ValidationView }) {
  return (
    <span className={`validation-pill validation-${validation.tone}`}>
      {validationIcon(validation.tone)}
      <span>{validation.label}</span>
    </span>
  );
}

function validationIcon(tone: ValidationTone) {
  if (tone === "success") return <CheckCircle2 size={15} />;
  if (tone === "failed") return <TriangleAlert size={15} />;
  return <MinusCircle size={15} />;
}

function buildValidationView(event: TraceEvent | undefined, sql: string | null): ValidationView {
  const hasSql = Boolean(sql?.trim());
  if (!event) {
    return {
      label: hasSql ? "Not validated" : "No SQL",
      meta: hasSql ? "pending" : "idle",
      tone: "idle",
      error: null,
      limitApplied: null,
      referencedTables: [],
      safeSql: null,
    };
  }

  const valid = booleanOutput(event, "valid");
  const error = stringOutput(event, "error");
  const safeSql = stringOutput(event, "safe_sql");
  const limitApplied = numberOutput(event, "limit_applied");
  const referencedTables = stringArrayOutput(event, "referenced_tables");

  if (valid === true) {
    return {
      label: "Validated",
      meta: "validated",
      tone: "success",
      error: null,
      limitApplied,
      referencedTables,
      safeSql,
    };
  }

  if (valid === false || event.status === "failed") {
    return {
      label: "Validation failed",
      meta: "failed",
      tone: "failed",
      error: error || event.message || "SQL validation failed.",
      limitApplied,
      referencedTables,
      safeSql,
    };
  }

  return {
    label: statusLabel(event.status),
    meta: event.status,
    tone: event.status,
    error,
    limitApplied,
    referencedTables,
    safeSql,
  };
}

function statusLabel(status: TraceStatus): string {
  if (status === "running") return "Validating";
  if (status === "skipped") return "Skipped";
  if (status === "success") return "Validated";
  if (status === "failed") return "Validation failed";
  return "Pending";
}

function formatSql(sql: string): string {
  return sql
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\s+(FROM)\s+/gi, "\nFROM ")
    .replace(/\s+((?:LEFT|RIGHT|INNER|FULL|CROSS)\s+JOIN|JOIN)\s+/gi, "\n$1 ")
    .replace(/\s+(ON)\s+/gi, "\n  ON ")
    .replace(/\s+(WHERE)\s+/gi, "\nWHERE ")
    .replace(/\s+(GROUP BY)\s+/gi, "\nGROUP BY ")
    .replace(/\s+(HAVING)\s+/gi, "\nHAVING ")
    .replace(/\s+(ORDER BY)\s+/gi, "\nORDER BY ")
    .replace(/\s+(LIMIT)\s+/gi, "\nLIMIT ")
    .replace(/\s+(OFFSET)\s+/gi, "\nOFFSET ")
    .replace(/\s+(UNION ALL|UNION)\s+/gi, "\n$1\n")
    .replace(/\s+(AND|OR)\s+/gi, "\n  $1 ");
}

function findTraceEvent(trace: TraceEvent[], step: string): TraceEvent | undefined {
  return trace.find((event) => event.step === step);
}

function stringOutput(event: TraceEvent | undefined, key: string): string | null {
  const value = event?.output[key];
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function booleanOutput(event: TraceEvent, key: string): boolean | null {
  const value = event.output[key];
  return typeof value === "boolean" ? value : null;
}

function numberOutput(event: TraceEvent, key: string): number | null {
  const value = event.output[key];
  return typeof value === "number" ? value : null;
}

function stringArrayOutput(event: TraceEvent, key: string): string[] {
  const value = event.output[key];
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.length > 0);
}

async function copyText(text: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}
