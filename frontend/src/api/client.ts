import axios from "axios";

import type {
  ChatResponse,
  ClearSessionResponse,
  SessionHistoryResponse,
} from "../types/chat";
import type {
  DataTableDeleteResponse,
  DataTableListResponse,
  DataTableRowsResponse,
} from "../types/data";
import type {
  HealthResponse,
  SchemaMetadataResponse,
  SchemaRetrieveRequest,
  SchemaRetrieveResponse,
  TableListResponse,
  TableSchema,
} from "../types/schema";
import type { ImportCommitResponse, ImportPreviewResponse } from "../types/import";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
  timeout: Number(import.meta.env.VITE_API_TIMEOUT_MS || 180000),
});

export type RequestStatus = "idle" | "loading" | "success" | "error";

export type ApiRequestState<T> = {
  status: RequestStatus;
  data: T | null;
  error: string;
};

export class ApiClientError extends Error {
  statusCode?: number;
  code?: string;
  details?: unknown;

  constructor(message: string, statusCode?: number, details?: unknown, code?: string) {
    super(message);
    this.name = "ApiClientError";
    this.statusCode = statusCode;
    this.details = details;
    this.code = code;
  }
}

type APIErrorPayload = {
  code?: string;
  message?: string;
  details?: unknown;
};

export function createIdleState<T>(): ApiRequestState<T> {
  return {
    status: "idle",
    data: null,
    error: "",
  };
}

export function createLoadingState<T>(currentData: T | null = null): ApiRequestState<T> {
  return {
    status: "loading",
    data: currentData,
    error: "",
  };
}

export function createSuccessState<T>(data: T): ApiRequestState<T> {
  return {
    status: "success",
    data,
    error: "",
  };
}

export function createErrorState<T>(error: unknown, currentData: T | null = null): ApiRequestState<T> {
  return {
    status: "error",
    data: currentData,
    error: toApiClientError(error).message,
  };
}

export async function getHealth(): Promise<HealthResponse> {
  return request(() => api.get<HealthResponse>("/health"));
}

export async function getDatabaseHealth(): Promise<Record<string, unknown>> {
  return request(() => api.get<Record<string, unknown>>("/api/db/health"));
}

export async function getTables(): Promise<TableListResponse> {
  return request(() => api.get<TableListResponse>("/api/schema/tables"));
}

export async function getTableSchema(tableName: string): Promise<TableSchema> {
  return request(() => api.get<TableSchema>(`/api/schema/tables/${encodeURIComponent(tableName)}`));
}

export async function getSchemaMetadata(): Promise<SchemaMetadataResponse> {
  return request(() => api.get<SchemaMetadataResponse>("/api/schema/metadata"));
}

export async function retrieveSchema(requestBody: SchemaRetrieveRequest): Promise<SchemaRetrieveResponse> {
  return request(() => api.post<SchemaRetrieveResponse>("/api/schema/retrieve", requestBody));
}

export async function getDataTables(): Promise<DataTableListResponse> {
  return request(() => api.get<DataTableListResponse>("/api/data/tables"));
}

export async function getTableRows(tableName: string, limit = 50, offset = 0): Promise<DataTableRowsResponse> {
  return request(() =>
    api.get<DataTableRowsResponse>(`/api/data/tables/${encodeURIComponent(tableName)}/rows`, {
      params: { limit, offset },
    }),
  );
}

export async function deleteDataTables(tableNames: string[]): Promise<DataTableDeleteResponse> {
  return request(() =>
    api.delete<DataTableDeleteResponse>("/api/data/tables", {
      data: { table_names: tableNames },
    }),
  );
}

export async function sendQuestion(question: string, sessionId: string, selectedTableName?: string | null): Promise<ChatResponse> {
  return request(() =>
    api.post<ChatResponse>("/api/chat", {
      question,
      session_id: sessionId,
      selected_table_name: selectedTableName || null,
    }),
  );
}

export async function getSessionHistory(sessionId: string, limit = 10): Promise<SessionHistoryResponse> {
  return request(() =>
    api.get<SessionHistoryResponse>(`/api/sessions/${encodeURIComponent(sessionId)}/history`, {
      params: { limit },
    }),
  );
}

export async function clearSession(sessionId: string): Promise<ClearSessionResponse> {
  return request(() => api.delete<ClearSessionResponse>(`/api/sessions/${encodeURIComponent(sessionId)}`));
}

export async function previewImportFile(file: File, previewLimit = 50): Promise<ImportPreviewResponse> {
  const formData = new FormData();
  formData.append("file", file);

  return request(() =>
    api.post<ImportPreviewResponse>("/api/import/preview", formData, {
      params: { preview_limit: previewLimit },
    }),
  );
}

export async function commitImportFile(file: File, tableName: string): Promise<ImportCommitResponse> {
  const formData = new FormData();
  formData.append("table_name", tableName.trim());
  formData.append("file", file);

  return request(() => api.post<ImportCommitResponse>("/api/import/commit", formData));
}

async function request<T>(operation: () => Promise<{ data: T }>): Promise<T> {
  try {
    const response = await operation();
    return response.data;
  } catch (caught) {
    throw toApiClientError(caught);
  }
}

export function toApiClientError(caught: unknown): ApiClientError {
  if (caught instanceof ApiClientError) {
    return caught;
  }

  if (axios.isAxiosError(caught)) {
    const statusCode = caught.response?.status;
    const payload = extractApiErrorPayload(caught.response?.data);

    if (payload?.message) {
      return new ApiClientError(payload.message, statusCode, payload.details, payload.code);
    }

    if (caught.code === "ECONNABORTED") {
      return new ApiClientError("请求超时。请稍后重试，或确认大模型服务响应正常。", statusCode, caught.response?.data, "request_timeout");
    }

    if (!caught.response) {
      return new ApiClientError("无法连接后端服务。请确认 Docker 服务已经启动。", statusCode, undefined, "network_unavailable");
    }

    return new ApiClientError(readableStatusMessage(statusCode), statusCode, caught.response?.data);
  }

  if (caught instanceof Error) {
    return new ApiClientError(caught.message);
  }

  return new ApiClientError("请求失败");
}

function extractApiErrorPayload(data: unknown): APIErrorPayload | null {
  if (!isRecord(data)) return null;

  const standardError = data.error;
  if (isApiErrorPayload(standardError)) {
    return standardError;
  }

  const detail = data.detail;
  if (typeof detail === "string") {
    return { message: detail };
  }
  if (isRecord(detail) && isApiErrorPayload(detail.error)) {
    return detail.error;
  }
  if (isApiErrorPayload(detail)) {
    return detail;
  }

  return null;
}

function isApiErrorPayload(value: unknown): value is APIErrorPayload {
  return isRecord(value) && typeof value.message === "string";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function readableStatusMessage(statusCode?: number): string {
  if (statusCode === 404) return "请求的资源不存在。";
  if (statusCode === 422) return "请求内容不完整或格式不正确。";
  if (statusCode && statusCode >= 500) return "后端服务暂时不可用，请稍后重试。";
  return "请求失败，请稍后重试。";
}
