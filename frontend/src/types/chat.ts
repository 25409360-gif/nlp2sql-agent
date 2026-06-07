import type { JsonObject, TraceEvent } from "./trace";

export type QueryRow = JsonObject;

export type ChatRequest = {
  question: string;
  session_id: string;
  selected_table_name?: string | null;
};

export type ChatResponse = {
  status: string;
  answer: string;
  session_id: string;
  sql: string | null;
  columns: string[];
  rows: QueryRow[];
  row_count: number;
  trace: TraceEvent[];
  retrieved_schema: RetrievedSchemaItem[];
  error: string | null;
  error_code: string | null;
};

export type RetrievedSchemaItem = {
  table_name: string;
  columns: string[];
  score?: number;
  distance?: number | null;
  source?: string;
  content?: string;
};

export type SessionTurn = {
  question: string;
  answer: string;
  sql: string | null;
  status: string;
  error: string | null;
  summary: JsonObject | null;
  resolved_entities: JsonObject;
  retrieved_tables: string[];
  columns: string[];
  rows: QueryRow[];
  row_count: number;
  created_at: string;
};

export type SessionHistoryResponse = {
  session_id: string;
  turns: SessionTurn[];
  count: number;
};

export type ClearSessionResponse = {
  session_id: string;
  cleared: boolean;
};

export type ChatMessageRole = "user" | "assistant";

export type ChatMessage = {
  id: string;
  role: ChatMessageRole;
  content: string;
  status?: string;
  rowCount?: number;
  createdAt: string;
};
