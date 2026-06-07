from fastapi import APIRouter

from app.core.config import settings
from app.schemas.schema import (
    SchemaMetadataResponse,
    SchemaRetrieveRequest,
    SchemaRetrieveResponse,
    TableListResponse,
    TableSchema,
)
from app.services.schema_retriever import SchemaRetriever
from app.services.schema_service import SchemaService
from app.utils.error_handling import classify_error, http_error

router = APIRouter(prefix="/schema", tags=["schema"])


@router.get("/tables", response_model=TableListResponse)
def list_tables() -> TableListResponse:
    service = SchemaService()
    return TableListResponse(tables=service.list_tables())


@router.get("/tables/{table_name}", response_model=TableSchema)
def get_table_schema(table_name: str) -> TableSchema:
    service = SchemaService()
    schema = service.get_table_schema(table_name)
    if schema is None:
        raise http_error(
            status_code=404,
            code="not_found",
            message=f"没有找到数据表：{table_name}",
            details={"table_name": table_name},
        )
    return TableSchema(**schema)


@router.get("/metadata", response_model=SchemaMetadataResponse)
def get_schema_metadata() -> SchemaMetadataResponse:
    service = SchemaService()
    return SchemaMetadataResponse(schema=settings.db_schema, tables=service.get_metadata())


@router.post("/retrieve", response_model=SchemaRetrieveResponse)
def retrieve_schema(request: SchemaRetrieveRequest) -> SchemaRetrieveResponse:
    try:
        result = SchemaRetriever().retrieve(
            question=request.question,
            top_k=request.top_k,
            refresh_index=request.refresh_index,
            use_keyword_fallback=request.use_keyword_fallback,
            preferred_table_names=request.preferred_table_names,
            restrict_to_preferred=request.restrict_to_preferred,
        )
    except ValueError as exc:
        raise http_error(
            status_code=400,
            code="invalid_request",
            details={"reason": str(exc)},
        ) from exc
    except Exception as exc:
        error_info = classify_error(exc, failed_step="schema_retrieval")
        raise http_error(
            status_code=503,
            code=error_info.code,
            message=error_info.message,
            details=error_info.details,
        ) from exc

    return SchemaRetrieveResponse(**result)
