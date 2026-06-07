export type HealthResponse = {
  status: string;
  service: string;
  version: string;
};

export type TableSummary = {
  name: string;
  description: string;
};

export type TableColumn = {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
  description: string;
};

export type ForeignKey = {
  columns: string[];
  referred_schema: string;
  referred_table: string | null;
  referred_columns: string[];
};

export type TableIndex = {
  name: string | null;
  columns: string[];
  unique: boolean;
};

export type TableSchema = {
  name: string;
  schema: string;
  description: string;
  columns: TableColumn[];
  primary_keys: string[];
  foreign_keys: ForeignKey[];
  indexes: TableIndex[];
};

export type TableListResponse = {
  tables: TableSummary[];
};

export type SchemaMetadataResponse = {
  schema: string;
  tables: TableSchema[];
};

export type SchemaRetrieveRequest = {
  question: string;
  top_k?: number;
  refresh_index?: boolean;
  use_keyword_fallback?: boolean;
  preferred_table_names?: string[];
  restrict_to_preferred?: boolean;
};

export type SchemaMatch = {
  table_name: string;
  columns: string[];
  score: number;
  distance: number | null;
  source: string;
  content: string;
};

export type SchemaRetrieveResponse = {
  question: string;
  matches: SchemaMatch[];
};
