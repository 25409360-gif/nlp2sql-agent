from pathlib import PurePath

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.schemas.import_data import (
    SUPPORTED_IMPORT_EXTENSIONS,
    ImportCapabilitiesResponse,
    ImportCommitResponse,
    ImportPreviewResponse,
    ImportUploadCheckResponse,
)
from app.services.import_commit_service import (
    DuplicateImportTableError,
    EmptyImportDataError,
    ImportCommitError,
    ImportCommitService,
)
from app.services.import_preview_service import (
    DEFAULT_PREVIEW_ROW_LIMIT,
    EmptyImportFileError,
    ImportPreviewError,
    ImportPreviewService,
    UnsupportedImportFileError,
    extension_from_filename,
)
from app.services.table_data_safety import InvalidTableNameError
from app.utils.error_handling import classify_error, http_error


router = APIRouter(prefix="/import", tags=["import"])


def create_import_preview_service() -> ImportPreviewService:
    return ImportPreviewService()


def create_import_commit_service() -> ImportCommitService:
    return ImportCommitService()


@router.get("/capabilities", response_model=ImportCapabilitiesResponse)
def get_import_capabilities() -> ImportCapabilitiesResponse:
    return ImportCapabilitiesResponse(
        supported_extensions=list(SUPPORTED_IMPORT_EXTENSIONS),
        upload_ready=True,
    )


@router.post("/upload-check", response_model=ImportUploadCheckResponse)
async def check_uploaded_file(file: UploadFile = File(...)) -> ImportUploadCheckResponse:
    filename = PurePath(file.filename or "").name
    extension = extension_from_filename(filename)
    if not filename:
        raise http_error(
            status_code=400,
            code="invalid_request",
            message="上传文件名不能为空。",
        )
    if extension not in SUPPORTED_IMPORT_EXTENSIONS:
        raise http_error(
            status_code=400,
            code="invalid_request",
            message="只支持上传 CSV 或 XLSX 文件。",
            details={"filename": filename, "extension": extension},
        )

    content = await file.read()
    return ImportUploadCheckResponse(
        filename=filename,
        extension=extension,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        supported=True,
    )


@router.post("/preview", response_model=ImportPreviewResponse)
async def preview_uploaded_file(
    file: UploadFile = File(...),
    preview_limit: int = Query(default=DEFAULT_PREVIEW_ROW_LIMIT, ge=1, le=500),
    service: ImportPreviewService = Depends(create_import_preview_service),
) -> ImportPreviewResponse:
    filename = PurePath(file.filename or "").name
    content = await file.read()
    try:
        preview = service.preview_file(
            filename=filename,
            content=content,
            content_type=file.content_type or "",
            preview_limit=preview_limit,
        )
    except UnsupportedImportFileError as exc:
        raise http_error(
            status_code=400,
            code="invalid_request",
            message=str(exc),
            details={"filename": filename, "extension": extension_from_filename(filename)},
        ) from exc
    except EmptyImportFileError as exc:
        raise http_error(
            status_code=400,
            code="invalid_request",
            message=str(exc),
            details={"filename": filename},
        ) from exc
    except ImportPreviewError as exc:
        raise http_error(
            status_code=400,
            code="invalid_request",
            message=str(exc),
            details={"filename": filename},
        ) from exc

    return ImportPreviewResponse(**preview)


@router.post("/commit", response_model=ImportCommitResponse)
async def commit_uploaded_file(
    table_name: str = Form(...),
    file: UploadFile = File(...),
    service: ImportCommitService = Depends(create_import_commit_service),
) -> ImportCommitResponse:
    filename = PurePath(file.filename or "").name
    content = await file.read()
    try:
        result = service.commit_file(
            table_name=table_name,
            filename=filename,
            content=content,
            content_type=file.content_type or "",
        )
    except DuplicateImportTableError as exc:
        raise http_error(
            status_code=409,
            code="invalid_request",
            message=str(exc),
            details={"table_name": table_name},
        ) from exc
    except (InvalidTableNameError, EmptyImportDataError, ImportCommitError, ImportPreviewError) as exc:
        raise http_error(
            status_code=400,
            code="invalid_request",
            message=str(exc),
            details={"table_name": table_name, "filename": filename},
        ) from exc
    except Exception as exc:
        error_info = classify_error(exc, default_code="internal_error")
        raise http_error(
            status_code=500,
            code=error_info.code,
            message=error_info.message,
            details=error_info.details,
        ) from exc

    return ImportCommitResponse(**result)
