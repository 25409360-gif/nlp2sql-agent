export type JsonPrimitive = string | number | boolean | null;

export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export type DataTableSummary = {
  name: string;
  description: string;
  column_count: number;
  deletable: boolean;
};

export type DataTableListResponse = {
  tables: DataTableSummary[];
};

export type DataTableDeleteResponse = {
  deleted_tables: string[];
  deleted_count: number;
  schema_refresh: Record<string, JsonValue>;
};

export type DataTableRow = Record<string, JsonValue>;

export type DataTableRowsResponse = {
  table_name: string;
  columns: string[];
  rows: DataTableRow[];
  limit: number;
  offset: number;
  row_count: number;
  total_count: number;
};
