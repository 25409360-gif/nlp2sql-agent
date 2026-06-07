from typing import Any

from pydantic import BaseModel, Field


SUPPORTED_IMPORT_EXTENSIONS = ("csv", "xlsx")


class ImportCapabilitiesResponse(BaseModel):
    supported_extensions: list[str]
    upload_ready: bool = True


class ImportUploadCheckResponse(BaseModel):
    filename: str
    extension: str
    content_type: str
    size_bytes: int = Field(ge=0)
    supported: bool


class ImportPreviewColumn(BaseModel):
    name: str
    original_name: str
    type: str
    nullable: bool
    sample_values: list[Any] = Field(default_factory=list)


class ImportPreviewResponse(BaseModel):
    filename: str
    extension: str
    content_type: str
    sheet_name: str | None = None
    encoding: str | None = None
    columns: list[ImportPreviewColumn]
    rows: list[dict[str, Any]]
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    preview_row_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class ImportSchemaRefreshResponse(BaseModel):
    imported_table_visible: bool
    metadata_table_count: int = Field(ge=0)
    document_count: int = Field(ge=0)
    indexed_document_count: int = Field(ge=0)
    vector_inserted_count: int = Field(ge=0)


class ImportCommitResponse(BaseModel):
    filename: str
    extension: str
    schema_name: str
    table_name: str
    columns: list[ImportPreviewColumn]
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    created: bool
    warnings: list[str] = Field(default_factory=list)
    schema_refresh: ImportSchemaRefreshResponse
