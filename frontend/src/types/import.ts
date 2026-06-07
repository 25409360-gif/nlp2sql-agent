import type { JsonValue } from "./data";

export type ImportPreviewColumn = {
  name: string;
  original_name: string;
  type: string;
  nullable: boolean;
  sample_values: JsonValue[];
};

export type ImportPreviewResponse = {
  filename: string;
  extension: string;
  content_type: string;
  sheet_name: string | null;
  encoding: string | null;
  columns: ImportPreviewColumn[];
  rows: Record<string, JsonValue>[];
  row_count: number;
  column_count: number;
  preview_row_count: number;
  warnings: string[];
};

export type ImportSchemaRefreshResponse = {
  imported_table_visible: boolean;
  metadata_table_count: number;
  document_count: number;
  indexed_document_count: number;
  vector_inserted_count: number;
};

export type ImportCommitResponse = {
  filename: string;
  extension: string;
  schema_name: string;
  table_name: string;
  columns: ImportPreviewColumn[];
  row_count: number;
  column_count: number;
  created: boolean;
  warnings: string[];
  schema_refresh: ImportSchemaRefreshResponse;
};
