import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Database,
  FileSpreadsheet,
  Loader2,
  Table2,
  Upload,
} from "lucide-react";
import type { ChangeEvent, FormEvent, ReactNode } from "react";
import { useMemo, useState } from "react";

import { commitImportFile, previewImportFile, toApiClientError } from "../api/client";
import type { JsonValue } from "../types/data";
import type { ImportCommitResponse, ImportPreviewColumn, ImportPreviewResponse } from "../types/import";
import type { StatusState } from "../types/status";

const previewLimit = 50;

type ImportPageProps = {
  onImportComplete?: (tableName: string) => void;
  onViewImportedTable?: (tableName: string) => void;
};

export function ImportPage({ onImportComplete, onViewImportedTable }: ImportPageProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [tableName, setTableName] = useState("");
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [previewStatus, setPreviewStatus] = useState<StatusState>("idle");
  const [previewError, setPreviewError] = useState("");
  const [importStatus, setImportStatus] = useState<StatusState>("idle");
  const [importError, setImportError] = useState("");
  const [importResult, setImportResult] = useState<ImportCommitResponse | null>(null);

  const supportedFile = useMemo(() => (selectedFile ? isSupportedFile(selectedFile) : false), [selectedFile]);
  const normalizedTableName = tableName.trim();
  const canPreview = Boolean(selectedFile) && supportedFile && previewStatus !== "loading" && importStatus !== "loading";
  const canImport = Boolean(selectedFile && preview && normalizedTableName) && previewStatus !== "loading" && importStatus !== "loading";

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    setPreview(null);
    setPreviewError("");
    setPreviewStatus("idle");
    resetImportState();
    setTableName(file ? inferTableName(file.name) : "");

    if (file && !isSupportedFile(file)) {
      setPreviewError("只支持 CSV 或 XLSX 文件。");
      setPreviewStatus("error");
    }
  }

  function handleTableNameChange(value: string) {
    setTableName(value);
    resetImportState();
  }

  async function handlePreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) {
      setPreviewError("请选择文件。");
      setPreviewStatus("error");
      return;
    }
    if (!supportedFile) {
      setPreviewError("只支持 CSV 或 XLSX 文件。");
      setPreviewStatus("error");
      return;
    }

    setPreviewStatus("loading");
    setPreviewError("");
    resetImportState();

    try {
      const result = await previewImportFile(selectedFile, previewLimit);
      setPreview(result);
      setPreviewStatus("ok");
    } catch (caught) {
      setPreview(null);
      setPreviewStatus("error");
      setPreviewError(toApiClientError(caught).message);
    }
  }

  async function handleImport() {
    if (!selectedFile || !preview) {
      setImportError("请先生成预览。");
      setImportStatus("error");
      return;
    }
    if (!normalizedTableName) {
      setImportError("请输入目标表名。");
      setImportStatus("error");
      return;
    }

    setImportStatus("loading");
    setImportError("");
    setImportResult(null);

    try {
      const result = await commitImportFile(selectedFile, normalizedTableName);
      setImportResult(result);
      setImportStatus("ok");
      onImportComplete?.(result.table_name);
    } catch (caught) {
      setImportStatus("error");
      setImportError(toApiClientError(caught).message);
    }
  }

  function resetImportState() {
    setImportStatus("idle");
    setImportError("");
    setImportResult(null);
  }

  return (
    <section className="import-workspace">
      <aside className="panel import-control-panel">
        <div className="panel-title">
          <span className="panel-title-icon">
            <Upload size={18} />
          </span>
          <span>Upload</span>
          <strong>{statusLabel(previewStatus, importStatus)}</strong>
        </div>

        <form className="import-form" onSubmit={(event) => void handlePreview(event)}>
          <label className="import-field">
            <span>文件</span>
            <input accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" type="file" onChange={handleFileChange} />
          </label>

          <label className="import-field">
            <span>目标表名</span>
            <input
              type="text"
              value={tableName}
              onChange={(event) => handleTableNameChange(event.target.value)}
              placeholder="uploaded_table"
              spellCheck={false}
            />
          </label>

          <div className="import-action-row">
            <button className="primary-import-button" type="submit" disabled={!canPreview}>
              {previewStatus === "loading" ? <Loader2 className="spin-icon" size={16} /> : <FileSpreadsheet size={16} />}
              <span>{previewStatus === "loading" ? "解析中" : "预览"}</span>
            </button>
            <button className="commit-import-button" type="button" onClick={() => void handleImport()} disabled={!canImport}>
              {importStatus === "loading" ? <Loader2 className="spin-icon" size={16} /> : <Database size={16} />}
              <span>{importStatus === "loading" ? "导入中" : "确认导入"}</span>
            </button>
          </div>
        </form>

        <div className="import-file-summary">
          <ImportMetaItem label="文件名" value={selectedFile?.name || "-"} />
          <ImportMetaItem label="大小" value={selectedFile ? formatFileSize(selectedFile.size) : "-"} />
          <ImportMetaItem label="格式" value={selectedFile ? fileExtension(selectedFile.name).toUpperCase() || "-" : "-"} />
        </div>

        {previewError ? <ImportInlineState icon={<AlertCircle size={18} />} title="无法预览文件" detail={previewError} tone="error" /> : null}
        {previewStatus === "ok" && preview ? (
          <ImportInlineState icon={<CheckCircle2 size={18} />} title="预览已生成" detail={`${preview.row_count} rows, ${preview.column_count} columns`} />
        ) : null}
        {renderImportState(importStatus, importResult, importError, onViewImportedTable)}
      </aside>

      <section className="panel import-preview-panel">
        <div className="import-preview-header">
          <div className="table-browser-title">
            <span className="panel-title-icon">
              <Table2 size={18} />
            </span>
            <div>
              <h2>{preview?.filename || "文件预览"}</h2>
              <p>{preview ? previewMetaText(preview) : "CSV / XLSX"}</p>
            </div>
          </div>
        </div>

        <div className="result-toolbar import-preview-toolbar">
          <span className="result-meta-chip">{preview ? `${preview.row_count} rows` : "No preview"}</span>
          <span className="result-meta-chip">{preview ? `${preview.column_count} columns` : "0 columns"}</span>
          <span className="result-meta-chip">{preview ? `${preview.preview_row_count} preview` : `${previewLimit} limit`}</span>
          {preview?.sheet_name ? <span className="result-meta-chip">{preview.sheet_name}</span> : null}
          {preview?.encoding ? <span className="result-meta-chip">{preview.encoding}</span> : null}
        </div>

        <div className="import-preview-body">
          {renderPreviewContent(previewStatus, preview)}
        </div>
      </section>

      <section className="panel import-fields-panel">
        <div className="panel-title">
          <span className="panel-title-icon">
            <FileSpreadsheet size={18} />
          </span>
          <span>Fields</span>
          <strong>{preview?.columns.length ?? 0}</strong>
        </div>
        {renderFieldsContent(previewStatus, preview?.columns ?? [])}
      </section>
    </section>
  );
}

function renderPreviewContent(status: StatusState, preview: ImportPreviewResponse | null) {
  if (status === "loading") {
    return <ImportEmptyState icon={<Loader2 className="spin-icon" size={24} />} title="正在解析文件" />;
  }
  if (!preview) {
    return <ImportEmptyState icon={<Upload size={24} />} title="尚未生成预览" />;
  }

  return (
    <>
      {preview.warnings.length > 0 ? (
        <div className="import-warning-list">
          {preview.warnings.map((warning, index) => (
            <span key={`${warning}-${index}`}>{warning}</span>
          ))}
        </div>
      ) : null}
      <PreviewTable preview={preview} />
    </>
  );
}

function renderFieldsContent(status: StatusState, columns: ImportPreviewColumn[]) {
  if (status === "loading") {
    return <ImportEmptyState icon={<Loader2 className="spin-icon" size={22} />} title="正在识别字段" compact />;
  }
  if (columns.length === 0) {
    return <ImportEmptyState icon={<FileSpreadsheet size={22} />} title="没有字段预览" compact />;
  }

  return (
    <div className="import-field-list">
      {columns.map((column) => (
        <div className="import-field-row" key={column.name}>
          <div>
            <strong title={column.name}>{column.name}</strong>
            <span title={column.original_name || column.name}>{column.original_name || column.name}</span>
          </div>
          <em>{column.type}</em>
        </div>
      ))}
    </div>
  );
}

function PreviewTable({ preview }: { preview: ImportPreviewResponse }) {
  if (preview.rows.length === 0) {
    return <ImportEmptyState icon={<Table2 size={24} />} title="没有可预览的数据行" />;
  }

  const columns = preview.columns.map((column) => column.name);
  return (
    <div className="result-table-scroll import-table-scroll">
      <table className="result-table import-preview-table">
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
          {preview.rows.map((row, rowIndex) => (
            <tr key={`import-row-${rowIndex}`}>
              {columns.map((column) => {
                const value = row[column];
                const text = formatValue(value);
                return (
                  <td key={column} className={value === null || typeof value === "undefined" ? "result-cell-null" : ""} title={text}>
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

function ImportMetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="import-meta-item">
      <span>{label}</span>
      <strong title={value}>{value}</strong>
    </div>
  );
}

function ImportInlineState({ icon, title, detail, tone = "info" }: { icon: ReactNode; title: string; detail?: string; tone?: "info" | "error" }) {
  return (
    <div className={`table-browser-inline-state import-inline-state ${tone === "error" ? "error" : ""}`}>
      {icon}
      <div>
        <strong>{title}</strong>
        {detail ? <span>{detail}</span> : null}
      </div>
    </div>
  );
}

function renderImportState(
  status: StatusState,
  result: ImportCommitResponse | null,
  error: string,
  onViewImportedTable?: (tableName: string) => void,
) {
  if (status === "loading") {
    return <ImportInlineState icon={<Loader2 className="spin-icon" size={18} />} title="正在导入数据库" detail="schema refresh" />;
  }
  if (status === "error") {
    return <ImportInlineState icon={<AlertCircle size={18} />} title="导入失败" detail={error} tone="error" />;
  }
  if (status !== "ok" || !result) {
    return null;
  }

  return (
    <div className="import-result-summary">
      <div>
        <CheckCircle2 size={18} />
        <strong title={result.table_name}>{result.table_name}</strong>
      </div>
      <dl>
        <dt>行数</dt>
        <dd>{result.row_count}</dd>
        <dt>字段</dt>
        <dd>{result.column_count}</dd>
        <dt>结构</dt>
        <dd>{result.schema_refresh.imported_table_visible ? "已刷新" : "待刷新"}</dd>
      </dl>
      <button className="secondary-button import-view-table-button" type="button" onClick={() => onViewImportedTable?.(result.table_name)}>
        <span>查看数据表</span>
        <ArrowRight size={15} />
      </button>
    </div>
  );
}

function ImportEmptyState({ icon, title, compact = false }: { icon: ReactNode; title: string; compact?: boolean }) {
  return (
    <div className={`result-empty ${compact ? "result-empty-compact" : ""}`}>
      {icon}
      <strong>{title}</strong>
    </div>
  );
}

function previewMetaText(preview: ImportPreviewResponse) {
  const parts = [preview.extension.toUpperCase()];
  if (preview.sheet_name) parts.push(preview.sheet_name);
  if (preview.encoding) parts.push(preview.encoding);
  return parts.join(" / ");
}

function statusLabel(previewStatus: StatusState, importStatus: StatusState) {
  if (importStatus === "loading") return "importing";
  if (importStatus === "ok") return "imported";
  if (importStatus === "error") return "import_error";
  if (previewStatus === "loading") return "loading";
  if (previewStatus === "ok") return "ready";
  if (previewStatus === "error") return "error";
  return "idle";
}

function inferTableName(filename: string) {
  const baseName = filename.replace(/\.[^.]+$/, "");
  const normalized = baseName
    .normalize("NFKD")
    .replace(/[^\w]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/_+/g, "_")
    .toLowerCase();
  const safeName = normalized || "uploaded_table";
  return /^\d/.test(safeName) ? `table_${safeName}` : safeName;
}

function isSupportedFile(file: File) {
  return ["csv", "xlsx"].includes(fileExtension(file.name));
}

function fileExtension(filename: string) {
  const match = filename.toLowerCase().match(/\.([a-z0-9]+)$/);
  return match?.[1] ?? "";
}

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function formatValue(value: JsonValue | undefined) {
  if (value === null || typeof value === "undefined") return "NULL";
  if (Array.isArray(value)) return JSON.stringify(value);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
