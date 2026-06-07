import { Clock3, Database, Table2 } from "lucide-react";
import { useMemo } from "react";

import type { ChatResponse, QueryRow } from "../types/chat";
import type { JsonValue, TraceEvent } from "../types/trace";

type ResultTableProps = {
  result: ChatResponse | null;
};

const maxPreviewRows = 100;

export function ResultTable({ result }: ResultTableProps) {
  const executionEvent = useMemo(() => findTraceEvent(result?.trace ?? [], "sql_execution"), [result]);
  const columns = result?.columns ?? [];
  const rows = result?.rows ?? [];
  const rowCount = result?.row_count ?? 0;
  const visibleRows = rows.slice(0, maxPreviewRows);
  const executionMs = typeof executionEvent?.duration_ms === "number" ? executionEvent.duration_ms : null;
  const truncated = booleanOutput(executionEvent, "truncated") === true || rows.length > maxPreviewRows;
  const meta = result ? `${rowCount} ${rowCount === 1 ? "row" : "rows"}` : "idle";

  return (
    <section className="panel result-panel result-table-panel">
      <div className="panel-title">
        <span className="panel-title-icon">
          <Table2 size={18} />
        </span>
        <span>Result</span>
        <strong>{meta}</strong>
      </div>

      <div className="result-table-body">
        <div className="result-toolbar">
          <span className="result-meta-chip">
            <Database size={14} />
            {result ? `${rowCount} ${rowCount === 1 ? "row" : "rows"}` : "No result"}
          </span>
          <span className="result-meta-chip">{columns.length} columns</span>
          {executionMs !== null && (
            <span className="result-meta-chip">
              <Clock3 size={14} />
              {formatDuration(executionMs)}
            </span>
          )}
          {truncated && <span className="result-meta-chip result-meta-warning">truncated</span>}
        </div>

        {renderResultContent(result, columns, visibleRows, rowCount, truncated)}
      </div>
    </section>
  );
}

function renderResultContent(
  result: ChatResponse | null,
  columns: string[],
  rows: QueryRow[],
  rowCount: number,
  truncated: boolean,
) {
  if (!result) {
    return <ResultEmpty title="尚无结果" detail="提交查询后会显示数据表。" />;
  }

  if (columns.length === 0) {
    return <ResultEmpty title={result.status === "success" ? "没有返回列" : "查询未返回结果"} detail={result.error ?? result.answer} />;
  }

  if (rows.length === 0) {
    return (
      <>
        <div className="result-table-scroll result-table-scroll-empty">
          <table className="result-table">
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column} title={column}>
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
          </table>
        </div>
        <ResultEmpty title="没有匹配的行" detail="SQL 执行成功，但结果集为空。" compact />
      </>
    );
  }

  return (
    <>
      <div className="result-table-scroll">
        <table className="result-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column} title={column}>
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={`row-${rowIndex}`}>
                {columns.map((column) => {
                  const value = row[column];
                  const text = formatCellValue(value);
                  return (
                    <td className={value === null || typeof value === "undefined" ? "result-cell-null" : ""} key={column} title={text}>
                      <span className="result-cell-value">{text}</span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(truncated || rows.length < rowCount) && (
        <div className="result-footnote">
          {truncated ? `Showing first ${rows.length} rows. Result was truncated.` : `Showing ${rows.length} of ${rowCount} returned rows.`}
        </div>
      )}
    </>
  );
}

function ResultEmpty({ title, detail, compact = false }: { title: string; detail: string; compact?: boolean }) {
  return (
    <div className={`result-empty ${compact ? "result-empty-compact" : ""}`}>
      <Database size={22} />
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  );
}

function findTraceEvent(trace: TraceEvent[], step: string): TraceEvent | undefined {
  return trace.find((event) => event.step === step);
}

function booleanOutput(event: TraceEvent | undefined, key: string): boolean | null {
  const value = event?.output[key];
  return typeof value === "boolean" ? value : null;
}

function formatDuration(durationMs: number): string {
  if (durationMs >= 1000) {
    return `${(durationMs / 1000).toFixed(1)}s`;
  }
  return `${Math.max(1, Math.round(durationMs))}ms`;
}

function formatCellValue(value: JsonValue | undefined): string {
  if (value === null || typeof value === "undefined") return "NULL";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}
