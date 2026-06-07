export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };
export type JsonObject = { [key: string]: JsonValue };

export type TraceStatus = "pending" | "running" | "success" | "failed" | "skipped";

export type TraceEvent = {
  step: string;
  status: TraceStatus;
  input: JsonObject;
  output: JsonObject;
  message: string;
  duration_ms: number | null;
};
