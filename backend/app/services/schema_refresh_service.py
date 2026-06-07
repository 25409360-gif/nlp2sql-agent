from typing import Any

from app.services.schema_document_service import SchemaDocumentService
from app.services.schema_retriever import SchemaRetriever
from app.services.schema_service import SchemaService


class SchemaRefreshService:
    def refresh_after_import(self, table_name: str) -> dict[str, Any]:
        result = self.refresh_schema()
        table_names = set(result.pop("table_names"))
        return {
            "imported_table_visible": table_name in table_names,
            **result,
        }

    def refresh_after_table_delete(self, table_names: list[str]) -> dict[str, Any]:
        result = self.refresh_schema()
        remaining_table_names = set(result.pop("table_names"))
        deleted_tables = [table_name for table_name in table_names if table_name not in remaining_table_names]
        return {
            "deleted_tables_absent": len(deleted_tables) == len(set(table_names)),
            "deleted_tables": deleted_tables,
            **result,
        }

    def refresh_schema(self) -> dict[str, Any]:
        SchemaService.clear_cache()
        schema_service = SchemaService()
        _clear_inspector_cache(schema_service)

        metadata = schema_service.get_metadata(refresh=True)
        document_service = SchemaDocumentService(schema_service)
        documents = document_service.build_documents(refresh=True)
        index_result = SchemaRetriever(
            schema_service=schema_service,
            document_service=document_service,
        ).index_schema(refresh=True, reset=True)

        table_names = {table["name"] for table in metadata}
        return {
            "table_names": sorted(table_names),
            "metadata_table_count": len(metadata),
            "document_count": len(documents),
            "indexed_document_count": int(index_result.get("documents") or 0),
            "vector_inserted_count": int(index_result.get("inserted") or 0),
        }


def _clear_inspector_cache(schema_service: SchemaService) -> None:
    clear_cache = getattr(getattr(schema_service, "inspector", None), "clear_cache", None)
    if callable(clear_cache):
        clear_cache()
