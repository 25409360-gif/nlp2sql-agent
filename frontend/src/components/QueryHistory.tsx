import { History, RotateCw, Trash2 } from "lucide-react";

import type { SessionTurn } from "../types/chat";

type QueryHistoryProps = {
  turns: SessionTurn[];
  selectedTurnId: string;
  isLoading: boolean;
  isClearing: boolean;
  error: string;
  onSelect: (turn: SessionTurn) => void;
  onRefresh: () => void;
  onClear: () => void;
};

export function QueryHistory({
  turns,
  selectedTurnId,
  isLoading,
  isClearing,
  error,
  onSelect,
  onRefresh,
  onClear,
}: QueryHistoryProps) {
  const visibleTurns = [...turns].reverse();

  return (
    <div className="history-box">
      <div className="panel-title history-title">
        <span className="panel-title-icon">
          <History size={16} />
        </span>
        <span>History</span>
        <strong>{turns.length}</strong>
        <button
          className="history-icon-button"
          disabled={isLoading}
          type="button"
          title="刷新历史"
          aria-label="刷新历史"
          onClick={onRefresh}
        >
          <RotateCw className={isLoading ? "spin-icon" : ""} size={15} />
        </button>
        <button
          className="history-icon-button"
          disabled={isClearing || turns.length === 0}
          type="button"
          title="清空历史"
          aria-label="清空历史"
          onClick={onClear}
        >
          <Trash2 size={15} />
        </button>
      </div>

      <div className="history-list">
        {visibleTurns.map((turn) => {
          const turnId = turnIdFor(turn);
          const isSelected = turnId === selectedTurnId;
          return (
            <article className={`history-card ${isSelected ? "active" : ""}`} key={turnId}>
              <button className="history-item" type="button" onClick={() => onSelect(turn)}>
                <span className="history-question" title={turn.question}>
                  {turn.question}
                </span>
                <span className="history-meta">
                  <strong>{turn.status || "unknown"}</strong>
                  <em>{turn.row_count} rows</em>
                  <em>{formatTime(turn.created_at)}</em>
                  {turn.columns?.length > 0 && <em>{turn.columns.length} columns</em>}
                </span>
                <span className="history-answer-preview" title={turn.answer || ""}>
                  {turn.answer || "暂无回答"}
                </span>
              </button>

              {isSelected && (
                <div className="history-detail">
                  <p>{turn.answer || "暂无回答"}</p>
                  {turn.sql && <pre>{turn.sql}</pre>}
                  {turn.retrieved_tables.length > 0 && (
                    <div className="history-table-tags">
                      {turn.retrieved_tables.slice(0, 5).map((table) => (
                        <span key={table}>{table}</span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </article>
          );
        })}

        {visibleTurns.length === 0 && <div className="history-empty">{isLoading ? "正在加载历史" : "暂无历史"}</div>}
        {error && <div className="history-error">{error}</div>}
      </div>
    </div>
  );
}

export function turnIdFor(turn: SessionTurn): string {
  return `${turn.created_at}:${turn.question}`;
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}
