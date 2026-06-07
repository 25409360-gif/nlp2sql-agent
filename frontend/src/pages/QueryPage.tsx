import { Activity, MessageSquare, Workflow } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import {
  clearSession,
  getSchemaMetadata,
  getSessionHistory,
  sendQuestion,
  toApiClientError,
} from "../api/client";
import { ChatPanel } from "../components/ChatPanel";
import { QueryHistory, turnIdFor } from "../components/QueryHistory";
import { ResultTable } from "../components/ResultTable";
import { SchemaPanel } from "../components/SchemaPanel";
import { SQLViewer } from "../components/SQLViewer";
import { TracePanel } from "../components/TracePanel";
import type { ChatMessage, ChatResponse, SessionTurn } from "../types/chat";
import type { HealthResponse, TableSchema } from "../types/schema";
import type { StatusState } from "../types/status";
import type { TraceEvent } from "../types/trace";

type QueryPageProps = {
  backendStatus: StatusState;
  databaseStatus: StatusState;
  health: HealthResponse | null;
  refreshSignal: number;
  shellError: string;
};

const exampleQuestions = ["谁迟到次数最多？", "哪些项目任务还没完成？", "设备使用时长最高的是哪个项目？"];
const sessionStorageKey = "nlp2sql-agent-session-id";

export function QueryPage({ backendStatus, databaseStatus, health, refreshSignal, shellError }: QueryPageProps) {
  const [tables, setTables] = useState<TableSchema[]>([]);
  const [selectedTableName, setSelectedTableName] = useState<string>("");
  const [schemaStatus, setSchemaStatus] = useState<StatusState>("idle");
  const [schemaError, setSchemaError] = useState<string>("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatStatus, setChatStatus] = useState<StatusState>("idle");
  const [chatError, setChatError] = useState<string>("");
  const [sessionId] = useState(getOrCreateSessionId);
  const [lastChatResult, setLastChatResult] = useState<ChatResponse | null>(null);
  const [historyTurns, setHistoryTurns] = useState<SessionTurn[]>([]);
  const [historyStatus, setHistoryStatus] = useState<StatusState>("idle");
  const [historyError, setHistoryError] = useState("");
  const [selectedHistoryId, setSelectedHistoryId] = useState("");

  const highlightedTables = useMemo(
    () => lastChatResult?.retrieved_schema.map((item) => item.table_name) ?? [],
    [lastChatResult],
  );
  const selectedTable = useMemo(
    () => tables.find((table) => table.name === selectedTableName) ?? null,
    [selectedTableName, tables],
  );

  async function loadSchemaData() {
    setSchemaStatus("loading");
    setSchemaError("");

    try {
      const tableResult = await getSchemaMetadata();
      setTables(tableResult.tables);
      setSelectedTableName((current) =>
        current && tableResult.tables.some((table) => table.name === current) ? current : "",
      );
      setSchemaStatus("ok");
    } catch (caught) {
      const apiError = toApiClientError(caught);
      setSchemaStatus("error");
      setSchemaError(apiError.message);
    }
  }

  useEffect(() => {
    void loadSchemaData();
  }, [refreshSignal]);

  useEffect(() => {
    void loadHistory();
  }, [sessionId]);

  async function loadHistory() {
    setHistoryStatus("loading");
    setHistoryError("");
    try {
      const history = await getSessionHistory(sessionId, 10);
      setHistoryTurns(history.turns);
      setHistoryStatus("ok");
    } catch (caught) {
      setHistoryStatus("error");
      setHistoryError(toApiClientError(caught).message);
    }
  }

  async function submitQuestion(question: string) {
    const now = new Date().toISOString();
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: question,
      createdAt: now,
    };

    setChatMessages((current) => [...current, userMessage]);
    setChatStatus("loading");
    setChatError("");
    setLastChatResult(null);
    setSelectedHistoryId("");

    try {
      const result = await sendQuestion(question, sessionId, selectedTableName || null);
      const resultError = readableChatError(result.status, result.error);
      setLastChatResult(result);
      setChatMessages((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: result.answer || resultError || "查询完成。",
          status: result.status,
          rowCount: result.row_count,
          createdAt: new Date().toISOString(),
        },
      ]);
      setChatStatus(result.status === "success" ? "ok" : "error");
      setChatError(resultError);
      void loadHistory();
    } catch (caught) {
      const apiError = toApiClientError(caught);
      setChatStatus("error");
      setChatError(apiError.message);
      setChatMessages((current) => [
        ...current,
        {
          id: `assistant-error-${Date.now()}`,
          role: "assistant",
          content: apiError.message,
          status: "error",
          createdAt: new Date().toISOString(),
        },
      ]);
    }
  }

  function selectHistoryTurn(turn: SessionTurn) {
    setSelectedHistoryId(turnIdFor(turn));
    setLastChatResult(chatResponseFromHistoryTurn(turn, sessionId));
    setChatMessages([
      {
        id: `history-user-${turn.created_at}`,
        role: "user",
        content: turn.question,
        createdAt: turn.created_at,
      },
      {
        id: `history-assistant-${turn.created_at}`,
        role: "assistant",
        content: turn.answer,
        status: turn.status,
        rowCount: turn.row_count,
        createdAt: turn.created_at,
      },
    ]);
    setChatStatus(turn.status === "success" ? "ok" : "error");
    setChatError(readableChatError(turn.status, turn.error));
  }

  async function clearCurrentHistory() {
    setHistoryStatus("loading");
    setHistoryError("");
    try {
      await clearSession(sessionId);
      setHistoryTurns([]);
      setSelectedHistoryId("");
      setLastChatResult(null);
      setChatMessages([]);
      setChatStatus("idle");
      setChatError("");
      setHistoryStatus("ok");
    } catch (caught) {
      setHistoryStatus("error");
      setHistoryError(toApiClientError(caught).message);
    }
  }

  return (
    <section className="workspace">
      <SchemaPanel
        tables={tables}
        selectedTableName={selectedTableName}
        highlightedTables={highlightedTables}
        onSelectTable={setSelectedTableName}
      />

      <section className="workbench-main">
        <section className="panel chat-panel">
          <PanelHeader icon={<MessageSquare size={18} />} title="Chat" meta={chatStatus === "loading" ? "running" : "ready"} />
          <div className="query-scope-bar">
            <span>查询范围</span>
            <strong title={selectedTable?.name ?? "全部表"}>{selectedTable?.name ?? "全部表"}</strong>
            {selectedTableName && (
              <button className="scope-clear-button" type="button" onClick={() => setSelectedTableName("")}>
                清除选择
              </button>
            )}
          </div>
          <ChatPanel
            messages={chatMessages}
            examples={exampleQuestions}
            isLoading={chatStatus === "loading"}
            error={chatError}
            onSubmit={(question) => void submitQuestion(question)}
          />
        </section>

        <section className="sql-result-grid">
          <SQLViewer sql={lastChatResult?.sql ?? null} trace={lastChatResult?.trace ?? []} />

          <ResultTable result={lastChatResult} />
        </section>
      </section>

      <aside className="panel trace-sidebar">
        <PanelHeader icon={<Workflow size={18} />} title="Agent Trace" meta={chatStatus === "loading" ? "running" : (lastChatResult?.status ?? "idle")} />
        <TracePanel events={lastChatResult?.trace ?? []} isRunning={chatStatus === "loading"} />

        <QueryHistory
          turns={historyTurns}
          selectedTurnId={selectedHistoryId}
          isLoading={historyStatus === "loading"}
          isClearing={historyStatus === "loading"}
          error={historyError}
          onSelect={selectHistoryTurn}
          onRefresh={() => void loadHistory()}
          onClear={() => void clearCurrentHistory()}
        />

        <div className="runtime-box">
          <PanelHeader icon={<Activity size={16} />} title="Runtime" meta="" />
          <StatusRow label="Backend" status={backendStatus} value={health?.version ?? "-"} />
          <StatusRow label="Database" status={databaseStatus} value="PostgreSQL" />
          <StatusRow label="Schema" status={schemaStatus} value={`${tables.length}`} />
          {shellError && <div className="error-box">{shellError}</div>}
          {schemaError && <div className="error-box">{schemaError}</div>}
        </div>
      </aside>
    </section>
  );
}

function getOrCreateSessionId(): string {
  const fallback = `web-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

  try {
    const stored = window.localStorage.getItem(sessionStorageKey);
    if (stored) return stored;
    window.localStorage.setItem(sessionStorageKey, fallback);
  } catch {
    return fallback;
  }

  return fallback;
}

function chatResponseFromHistoryTurn(turn: SessionTurn, sessionId: string): ChatResponse {
  return {
    status: turn.status,
    answer: turn.answer,
    session_id: sessionId,
    sql: turn.sql,
    columns: turn.columns ?? [],
    rows: turn.rows ?? [],
    row_count: turn.row_count,
    trace: historyTraceForTurn(turn),
    retrieved_schema: turn.retrieved_tables.map((tableName) => ({
      table_name: tableName,
      columns: [],
      source: "history",
    })),
    error: turn.error,
    error_code: null,
  };
}

function readableChatError(status: string, error: string | null | undefined): string {
  if (status === "success") return "";
  if (error) return error;
  if (status === "unsupported") return "这个问题暂时不支持。我只能处理只读的数据查询。";
  if (status === "needs_clarification") return "这个问题还不够明确，请补充查询对象、时间范围或筛选条件。";
  if (status === "failed") return "查询处理失败，请稍后重试或换一种问法。";
  return "";
}

function historyTraceForTurn(turn: SessionTurn): TraceEvent[] {
  const hasSql = Boolean(turn.sql);
  const succeeded = turn.status === "success";
  const completedStatus = succeeded ? "success" : "skipped";
  const message = "Loaded from query history.";

  return [
    {
      step: "intent_analysis",
      status: completedStatus,
      input: { source: "history" },
      output: {
        intent_type: "history",
        tables: turn.retrieved_tables,
      },
      message,
      duration_ms: null,
    },
    {
      step: "schema_retrieval",
      status: turn.retrieved_tables.length > 0 ? completedStatus : "skipped",
      input: { source: "history" },
      output: {
        matches: turn.retrieved_tables.length,
        tables: turn.retrieved_tables,
        sources: ["history"],
      },
      message,
      duration_ms: null,
    },
    {
      step: "schema_context_enrichment",
      status: turn.retrieved_tables.length > 0 ? completedStatus : "skipped",
      input: { source: "history" },
      output: {
        tables: turn.retrieved_tables,
      },
      message,
      duration_ms: null,
    },
    {
      step: "sql_generation",
      status: hasSql ? completedStatus : "skipped",
      input: { source: "history" },
      output: {
        status: turn.status,
        sql: turn.sql,
        tables_used: turn.retrieved_tables,
        source: "history",
      },
      message,
      duration_ms: null,
    },
    {
      step: "sql_validation",
      status: hasSql ? (succeeded ? "success" : "failed") : "skipped",
      input: { source: "history" },
      output: {
        valid: hasSql ? succeeded : null,
        safe_sql: turn.sql,
        error: turn.error,
        referenced_tables: turn.retrieved_tables,
        limit_applied: null,
      },
      message,
      duration_ms: null,
    },
    {
      step: "sql_execution",
      status: succeeded ? "success" : "skipped",
      input: { source: "history" },
      output: {
        success: succeeded,
        row_count: turn.row_count,
        columns: turn.columns ?? [],
        truncated: false,
        error: turn.error,
      },
      message,
      duration_ms: null,
    },
    {
      step: "sql_repair",
      status: "skipped",
      input: { source: "history" },
      output: {
        status: "skipped",
      },
      message,
      duration_ms: null,
    },
    {
      step: "result_summary",
      status: turn.answer ? completedStatus : "skipped",
      input: { source: "history" },
      output: {
        row_count: turn.row_count,
        source: "history",
      },
      message,
      duration_ms: null,
    },
  ];
}

function PanelHeader({ icon, title, meta }: { icon: ReactNode; title: string; meta: string }) {
  return (
    <div className="panel-title">
      <span className="panel-title-icon">{icon}</span>
      <span>{title}</span>
      {meta && <strong>{meta}</strong>}
    </div>
  );
}

function StatusRow({ label, status, value }: { label: string; status: StatusState; value: string }) {
  return (
    <div className="status-row">
      <span className={`status-dot ${status}`} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
