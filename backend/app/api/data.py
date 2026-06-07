from fastapi import APIRouter, Depends, Query

from app.schemas.data import DataTableDeleteRequest, DataTableDeleteResponse, DataTableListResponse, DataTableRowsResponse
from app.services.table_data_safety import InvalidPaginationError, InvalidTableNameError, UnknownTableError
from app.services.table_data_service import ProtectedTableDeletionError, TableDataService, TableDeletionError
from app.utils.error_handling import classify_error, http_error


router = APIRouter(prefix="/data", tags=["data"])


def create_table_data_service() -> TableDataService:
    return TableDataService()


@router.get("/tables", response_model=DataTableListResponse)
def list_data_tables(
    service: TableDataService = Depends(create_table_data_service),
) -> DataTableListResponse:
    try:
        tables = service.list_tables()
    except Exception as exc:
        error_info = classify_error(exc, default_code="internal_error")
        raise http_error(
            status_code=_status_code_for_error(error_info.code),
            code=error_info.code,
            message=error_info.message,
            details=error_info.details,
        ) from exc

    return DataTableListResponse(tables=tables)


@router.get("/tables/{table_name}/rows", response_model=DataTableRowsResponse)
def get_table_rows(
    table_name: str,
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    service: TableDataService = Depends(create_table_data_service),
) -> DataTableRowsResponse:
    try:
        result = service.get_table_rows(table_name=table_name, limit=limit, offset=offset)
    except UnknownTableError as exc:
        raise http_error(
            status_code=404,
            code="not_found",
            message=f"没有找到数据表：{table_name}",
            details={"table_name": table_name},
        ) from exc
    except InvalidTableNameError as exc:
        raise http_error(
            status_code=400,
            code="invalid_request",
            message=f"数据表名称不合法：{table_name}",
            details={"table_name": table_name, "reason": str(exc)},
        ) from exc
    except InvalidPaginationError as exc:
        raise http_error(
            status_code=422,
            code="validation_error",
            details={"reason": str(exc)},
        ) from exc
    except Exception as exc:
        error_info = classify_error(exc, default_code="internal_error")
        raise http_error(
            status_code=_status_code_for_error(error_info.code),
            code=error_info.code,
            message=error_info.message,
            details=error_info.details,
        ) from exc

    return DataTableRowsResponse(**result)


@router.delete("/tables", response_model=DataTableDeleteResponse)
def delete_data_tables(
    request: DataTableDeleteRequest,
    service: TableDataService = Depends(create_table_data_service),
) -> DataTableDeleteResponse:
    try:
        result = service.delete_tables(request.table_names)
    except UnknownTableError as exc:
        raise http_error(
            status_code=404,
            code="not_found",
            message="没有找到要删除的数据表。",
            details={"table_names": request.table_names, "reason": str(exc)},
        ) from exc
    except InvalidTableNameError as exc:
        raise http_error(
            status_code=400,
            code="invalid_request",
            message="数据表名称不合法。",
            details={"table_names": request.table_names, "reason": str(exc)},
        ) from exc
    except ProtectedTableDeletionError as exc:
        raise http_error(
            status_code=409,
            code="protected_table",
            message="只能删除通过文件上传导入的数据表。",
            details={"table_names": request.table_names, "reason": str(exc)},
        ) from exc
    except TableDeletionError as exc:
        raise http_error(
            status_code=400,
            code="invalid_request",
            message="无法删除数据表。",
            details={"table_names": request.table_names, "reason": str(exc)},
        ) from exc
    except Exception as exc:
        error_info = classify_error(exc, default_code="internal_error")
        raise http_error(
            status_code=_status_code_for_error(error_info.code),
            code=error_info.code,
            message=error_info.message,
            details=error_info.details,
        ) from exc

    return DataTableDeleteResponse(**result)


def _status_code_for_error(code: str) -> int:
    if code == "database_unavailable":
        return 503
    return 500
