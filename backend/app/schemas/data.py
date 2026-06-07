from typing import Any

from pydantic import BaseModel, Field


class DataTableSummary(BaseModel):
    name: str
    description: str = ""
    column_count: int = Field(ge=0)
    deletable: bool = False


class DataTableListResponse(BaseModel):
    tables: list[DataTableSummary]


class DataTableDeleteRequest(BaseModel):
    table_names: list[str] = Field(min_length=1, max_length=20)


class DataTableDeleteResponse(BaseModel):
    deleted_tables: list[str]
    deleted_count: int = Field(ge=0)
    schema_refresh: dict[str, Any]


class DataTableRowsResponse(BaseModel):
    table_name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    row_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
