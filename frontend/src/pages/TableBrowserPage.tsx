import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Database,
  Loader2,
  Lock,
  RefreshCw,
  Table2,
  Trash2,
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import { deleteDataTables, getDataTables, getTableRows, toApiClientError } from "../api/client";
import type { DataTableRowsResponse, DataTableSummary, JsonValue } from "../types/data";
import type { StatusState } from "../types/status";

const pageSize = 50;

type TableBrowserPageProps = {
  preferredTableName?: string;
  refreshSignal?: number;
  onTablesDeleted?: (tableNames: string[]) => void;
};

export function TableBrowserPage({ preferredTableName = "", refreshSignal = 0, onTablesDeleted }: TableBrowserPageProps) {
  const [tables, setTables] = useState<DataTableSummary[]>([]);
  const [selectedTableName, setSelectedTableName] = useState("");
  const [tableListStatus, setTableListStatus] = useState<StatusState>("idle");
  const [tableListError, setTableListError] = useState("");
  const [rowsResult, setRowsResult] = useState<DataTableRowsResponse | null>(null);
  const [rowsStatus, setRowsStatus] = useState<StatusState>("idle");
  const [rowsError, setRowsError] = useState("");
  const [offset, setOffset] = useState(0);
  const [selectedDeleteTableNames, setSelectedDeleteTableNames] = useState<string[]>([]);
  const [deleteStatus, setDeleteStatus] = useState<StatusState>("idle");
  const [deleteError, setDeleteError] = useState("");

  const selectedTable = useMemo(
    () => tables.find((table) => table.name === selectedTableName) ?? null,
    [tables, selectedTableName],
  );
  const canGoPrevious = offset > 0 && rowsStatus !== "loading";
  const canGoNext = Boolean(
    rowsResult &&
      rowsStatus !== "loading" &&
      rowsResult.offset + rowsResult.row_count < rowsResult.total_count,
  );

  useEffect(() => {
    void loadTables(preferredTableName);
  }, [preferredTableName, refreshSignal]);

  useEffect(() => {
    if (!selectedTableName) {
      setRowsResult(null);
      setRowsStatus("idle");
      setRowsError("");
      return;
    }

    void loadRows(selectedTableName, offset);
  }, [selectedTableName, offset]);

  async function loadTables(targetTableName = "") {
    setTableListStatus("loading");
    setTableListError("");

    try {
      const response = await getDataTables();
      setTables(response.tables);
      setSelectedDeleteTableNames((current) => {
        const deletableNames = new Set(response.tables.filter((table) => table.deletable).map((table) => table.name));
        return current.filter((tableName) => deletableNames.has(tableName));
      });
      setSelectedTableName((current) => {
        if (targetTableName && response.tables.some((table) => table.name === targetTableName)) return targetTableName;
        if (response.tables.some((table) => table.name === current)) return current;
        return response.tables[0]?.name ?? "";
      });
      setOffset(0);
      setTableListStatus("ok");
    } catch (caught) {
      setTableListStatus("error");
      setTableListError(toApiClientError(caught).message);
    }
  }

  async function deleteSelectedTables() {
    const tableNames = selectedDeleteTableNames;
    if (tableNames.length === 0 || deleteStatus === "loading") return;

    const preview = tableNames.length <= 3 ? tableNames.join(", ") : `${tableNames.slice(0, 3).join(", ")} 等 ${tableNames.length} 张表`;
    const confirmed = window.confirm(`确定删除 ${preview}？这会删除整张表和里面所有数据。`);
    if (!confirmed) return;

    setDeleteStatus("loading");
    setDeleteError("");
    try {
      const result = await deleteDataTables(tableNames);
      const deletedSet = new Set(result.deleted_tables);
      setSelectedDeleteTableNames([]);
      if (selectedTableName && deletedSet.has(selectedTableName)) {
        setSelectedTableName("");
        setRowsResult(null);
        setRowsStatus("idle");
        setRowsError("");
      }
      await loadTables();
      onTablesDeleted?.(result.deleted_tables);
      setDeleteStatus("ok");
    } catch (caught) {
      setDeleteStatus("error");
      setDeleteError(toApiClientError(caught).message);
    }
  }

  async function loadRows(tableName: string, nextOffset: number) {
    setRowsStatus("loading");
    setRowsError("");

    try {
      const response = await getTableRows(tableName, pageSize, nextOffset);
      setRowsResult(response);
      setRowsStatus("ok");
    } catch (caught) {
      setRowsStatus("error");
      setRowsResult(null);
      setRowsError(toApiClientError(caught).message);
    }
  }

  function selectTable(tableName: string) {
    setSelectedTableName(tableName);
    setOffset(0);
  }

  function toggleDeleteSelection(table: DataTableSummary, checked: boolean) {
    if (!table.deletable) return;
    setSelectedDeleteTableNames((current) => {
      if (checked) return current.includes(table.name) ? current : [...current, table.name];
      return current.filter((tableName) => tableName !== table.name);
    });
  }

  function goPrevious() {
    setOffset((current) => Math.max(0, current - pageSize));
  }

  function goNext() {
    setOffset((current) => current + pageSize);
  }

  return (
    <section className="table-browser-workspace">
      <aside className="panel table-browser-sidebar">
        <div className="panel-title">
          <span className="panel-title-icon">
            <Database size={18} />
          </span>
          <span>Tables</span>
          <strong>{tableListStatus === "loading" ? "loading" : `${tables.length}`}</strong>
        </div>

        <div className="table-browser-sidebar-actions">
          <button className="secondary-button" type="button" onClick={() => void loadTables()} disabled={tableListStatus === "loading"}>
            <RefreshCw size={15} className={tableListStatus === "loading" ? "spin-icon" : ""} />
            <span>刷新</span>
          </button>
          <button
            className="danger-button"
            type="button"
            onClick={() => void deleteSelectedTables()}
            disabled={selectedDeleteTableNames.length === 0 || deleteStatus === "loading"}
          >
            <Trash2 size={15} className={deleteStatus === "loading" ? "spin-icon" : ""} />
            <span>删除</span>
          </button>
        </div>

        {renderTableListState(tableListStatus, tableListError, tables.length)}
        {deleteError && <InlineState icon={<AlertCircle size={18} />} title="删除失败" detail={deleteError} tone="error" />}

        <div className="table-browser-list" aria-label="数据表列表">
          {tables.map((table) => (
            <div
              className={`data-table-item ${selectedTableName === table.name ? "active" : ""}`}
              key={table.name}
            >
              {table.deletable ? (
                <input
                  aria-label={`选择删除 ${table.name}`}
                  checked={selectedDeleteTableNames.includes(table.name)}
                  className="table-delete-checkbox"
                  disabled={deleteStatus === "loading"}
                  title="选择删除"
                  type="checkbox"
                  onChange={(event) => toggleDeleteSelection(table, event.target.checked)}
                />
              ) : (
                <button
                  aria-label={`打开 ${table.name}`}
                  className="table-protected-indicator"
                  title="系统表受保护，可以浏览但不能删除"
                  type="button"
                  onClick={() => selectTable(table.name)}
                >
                  <Lock size={13} />
                </button>
              )}
              <button className="data-table-select-button" type="button" onClick={() => selectTable(table.name)}>
                <span title={table.name}>{table.name}</span>
                <strong>{table.column_count}</strong>
              </button>
            </div>
          ))}
        </div>
      </aside>

      <section className="panel table-browser-main">
        <div className="table-browser-header">
          <div className="table-browser-title">
            <span className="panel-title-icon">
              <Table2 size={18} />
            </span>
            <div>
              <h2>{selectedTableName || "数据表浏览"}</h2>
              <p>{selectedTable?.description || "Database table rows"}</p>
            </div>
          </div>

          <button
            className="icon-button"
            type="button"
            onClick={() => selectedTableName && void loadRows(selectedTableName, offset)}
            disabled={!selectedTableName || rowsStatus === "loading"}
            aria-label="刷新表格数据"
          >
            <RefreshCw size={18} className={rowsStatus === "loading" ? "spin-icon" : ""} />
          </button>
        </div>

        <div className="result-toolbar table-browser-toolbar">
          <span className="result-meta-chip">
            <Database size={14} />
            {rowsResult ? `${rowsResult.total_count} rows` : "No table"}
          </span>
          <span className="result-meta-chip">{selectedTable?.column_count ?? rowsResult?.columns.length ?? 0} columns</span>
          <span className="result-meta-chip">offset {rowsResult?.offset ?? offset}</span>
          <span className="result-meta-chip">limit {rowsResult?.limit ?? pageSize}</span>
        </div>

        <div className="table-browser-body">
          {renderRowsContent(rowsStatus, rowsError, rowsResult)}
        </div>

        <div className="table-browser-pagination">
          <button className="pagination-button" type="button" onClick={goPrevious} disabled={!canGoPrevious}>
            <ChevronLeft size={16} />
            <span>上一页</span>
          </button>
          <span className="pagination-status">
            {formatPaginationStatus(rowsResult)}
          </span>
          <button className="pagination-button" type="button" onClick={goNext} disabled={!canGoNext}>
            <span>下一页</span>
            <ChevronRight size={16} />
          </button>
        </div>
      </section>
    </section>
  );
}

function renderTableListState(status: StatusState, error: string, tableCount: number) {
  if (status === "loading" && tableCount === 0) {
    return <InlineState icon={<Loader2 className="spin-icon" size={18} />} title="正在加载数据表" />;
  }
  if (status === "error") {
    return <InlineState icon={<AlertCircle size={18} />} title="无法加载数据表" detail={error} tone="error" />;
  }
  if (status === "ok" && tableCount === 0) {
    return <InlineState icon={<Database size={18} />} title="没有可浏览的数据表" />;
  }
  return null;
}

function renderRowsContent(status: StatusState, error: string, result: DataTableRowsResponse | null) {
  if (status === "loading" && !result) {
    return <TableBrowserState icon={<Loader2 className="spin-icon" size={22} />} title="正在加载表格数据" />;
  }
  if (status === "error") {
    return <TableBrowserState icon={<AlertCircle size={22} />} title="无法加载表格数据" detail={error} tone="error" />;
  }
  if (!result) {
    return <TableBrowserState icon={<Database size={22} />} title="尚未选择数据表" />;
  }
  if (result.columns.length === 0) {
    return <TableBrowserState icon={<Database size={22} />} title="没有返回列" />;
  }
  if (result.rows.length === 0) {
    return (
      <>
        <DataGrid columns={result.columns} rows={[]} />
        <TableBrowserState icon={<Database size={22} />} title="这张表没有数据" compact />
      </>
    );
  }
  return <DataGrid columns={result.columns} rows={result.rows} />;
}

function DataGrid({ columns, rows }: { columns: string[]; rows: DataTableRowsResponse["rows"] }) {
  return (
    <div className="result-table-scroll table-browser-scroll">
      <table className="result-table table-browser-table">
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
            <tr key={`table-row-${rowIndex}`}>
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
  );
}

function InlineState({ icon, title, detail, tone }: { icon: ReactNode; title: string; detail?: string; tone?: "error" }) {
  return (
    <div className={`table-browser-inline-state ${tone === "error" ? "error" : ""}`}>
      {icon}
      <div>
        <strong>{title}</strong>
        {detail && <span>{detail}</span>}
      </div>
    </div>
  );
}

function TableBrowserState({
  icon,
  title,
  detail,
  tone,
  compact = false,
}: {
  icon: ReactNode;
  title: string;
  detail?: string;
  tone?: "error";
  compact?: boolean;
}) {
  return (
    <div className={`result-empty ${compact ? "result-empty-compact" : ""} ${tone === "error" ? "table-browser-state-error" : ""}`}>
      {icon}
      <strong>{title}</strong>
      {detail && <span>{detail}</span>}
    </div>
  );
}

function formatCellValue(value: JsonValue | undefined): string {
  if (value === null || typeof value === "undefined") return "NULL";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function formatPaginationStatus(result: DataTableRowsResponse | null): string {
  if (!result || result.row_count === 0) return "0 / 0";
  return `${result.offset + 1}-${result.offset + result.row_count} / ${result.total_count}`;
}
