from pydantic import BaseModel, Field


class TableSummary(BaseModel):
    name: str
    description: str


class ColumnMetadata(BaseModel):
    name: str
    type: str
    nullable: bool
    primary_key: bool
    description: str


class ForeignKeyMetadata(BaseModel):
    columns: list[str]
    referred_schema: str
    referred_table: str | None
    referred_columns: list[str]


class IndexMetadata(BaseModel):
    name: str | None
    columns: list[str]
    unique: bool


class TableSchema(BaseModel):
    name: str
    schema: str
    description: str
    columns: list[ColumnMetadata]
    primary_keys: list[str]
    foreign_keys: list[ForeignKeyMetadata]
    indexes: list[IndexMetadata]


class TableListResponse(BaseModel):
    tables: list[TableSummary]


class SchemaMetadataResponse(BaseModel):
    schema: str
    tables: list[TableSchema]


class SchemaRetrieveRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)
    refresh_index: bool = False
    use_keyword_fallback: bool = True
    preferred_table_names: list[str] = Field(default_factory=list)
    restrict_to_preferred: bool = False


class SchemaMatch(BaseModel):
    table_name: str
    columns: list[str]
    score: float
    distance: float | None = None
    source: str
    content: str


class SchemaRetrieveResponse(BaseModel):
    question: str
    matches: list[SchemaMatch]
