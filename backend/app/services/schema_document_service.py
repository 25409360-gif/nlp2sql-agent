from typing import Any

from app.services.schema_service import SchemaService


TABLE_BUSINESS_TERMS: dict[str, list[str]] = {
    "departments": ["部门", "组织", "团队", "研究组", "department"],
    "users": ["用户", "员工", "成员", "人员", "user", "employee"],
    "projects": ["项目", "课题", "研发项目", "project"],
    "project_members": ["项目成员", "参与人员", "项目角色", "project member"],
    "tasks": ["任务", "工时", "进度", "完成率", "task"],
    "attendance_records": ["考勤", "打卡", "出勤", "工时", "迟到", "加班", "attendance"],
    "devices": ["设备", "仪器", "服务器", "工作站", "device"],
    "device_usage_records": ["设备使用", "使用时长", "设备频率", "usage"],
    "meetings": ["会议", "纪要", "开会", "meeting"],
    "meeting_participants": ["参会人员", "会议参与", "participant"],
}


class SchemaDocumentService:
    def __init__(self, schema_service: SchemaService | None = None) -> None:
        self.schema_service = schema_service or SchemaService()

    def build_documents(self, refresh: bool = False) -> list[dict[str, Any]]:
        return [
            self.build_document_for_table(table_schema)
            for table_schema in self.schema_service.get_metadata(refresh=refresh)
        ]

    def build_document_for_table(self, table_schema: dict[str, Any]) -> dict[str, Any]:
        table_name = table_schema["name"]
        columns = table_schema.get("columns", [])
        foreign_keys = table_schema.get("foreign_keys", [])
        business_terms = TABLE_BUSINESS_TERMS.get(table_name, [])
        relationships = self._build_relationships(foreign_keys)

        content_parts = [
            f"Table: {table_name}",
            f"Description: {table_schema.get('description', '')}",
            f"Business terms: {', '.join(business_terms)}",
            "Columns:",
            *[
                f"- {column['name']} ({column['type']}): {column.get('description', '')}"
                for column in columns
            ],
            "Relationships:",
            *(relationships or ["- none"]),
        ]

        return {
            "id": f"schema:{table_schema.get('schema', 'public')}:table:{table_name}",
            "content": "\n".join(content_parts),
            "table_name": table_name,
            "columns": [column["name"] for column in columns],
            "relationships": relationships,
            "metadata": {
                "schema": table_schema.get("schema", "public"),
                "table_name": table_name,
                "description": table_schema.get("description", ""),
                "business_terms": business_terms,
                "column_count": len(columns),
                "foreign_key_count": len(foreign_keys),
                "document_type": "schema_table",
            },
        }

    def _build_relationships(self, foreign_keys: list[dict[str, Any]]) -> list[str]:
        relationships = []
        for foreign_key in foreign_keys:
            columns = ", ".join(foreign_key.get("columns", []))
            referred_table = foreign_key.get("referred_table") or ""
            referred_columns = ", ".join(foreign_key.get("referred_columns", []))
            relationships.append(f"- {columns} -> {referred_table}.{referred_columns}")
        return relationships
