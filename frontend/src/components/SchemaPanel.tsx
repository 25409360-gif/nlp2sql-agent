import { Database, Search, TableProperties } from "lucide-react";
import { useMemo, useState } from "react";

import type { TableSchema } from "../types/schema";

type SchemaPanelProps = {
  tables: TableSchema[];
  selectedTableName: string;
  highlightedTables: string[];
  onSelectTable: (tableName: string) => void;
};

export function SchemaPanel({ tables, selectedTableName, highlightedTables, onSelectTable }: SchemaPanelProps) {
  const [filter, setFilter] = useState("");
  const highlightedSet = useMemo(() => new Set(highlightedTables), [highlightedTables]);
  const normalizedFilter = filter.trim().toLowerCase();
  const filteredTables = useMemo(
    () =>
      tables.filter((table) => {
        if (!normalizedFilter) return true;
        return (
          table.name.toLowerCase().includes(normalizedFilter) ||
          table.description.toLowerCase().includes(normalizedFilter) ||
          table.columns.some((column) => column.name.toLowerCase().includes(normalizedFilter))
        );
      }),
    [normalizedFilter, tables],
  );
  const selectedTable = selectedTableName ? tables.find((table) => table.name === selectedTableName) ?? null : null;

  return (
    <aside className="panel schema-sidebar">
      <div className="panel-title">
        <span className="panel-title-icon">
          <Database size={18} />
        </span>
        <span>Schema</span>
        <strong>{tables.length} tables</strong>
      </div>

      <div className="schema-search">
        <Search size={16} />
        <input
          aria-label="筛选表或字段"
          placeholder="筛选表或字段"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />
      </div>

      <div className="table-nav">
        {filteredTables.map((table) => (
          <button
            className={tableClassName(table.name, selectedTableName, highlightedSet)}
            key={table.name}
            type="button"
            onClick={() => onSelectTable(table.name)}
          >
            <span>{table.name}</span>
            {highlightedSet.has(table.name) && <strong>hit</strong>}
          </button>
        ))}
        {filteredTables.length === 0 && <div className="schema-empty">没有匹配的表</div>}
      </div>

      <div className="schema-detail">
        <div className="schema-detail-title">
          <TableProperties size={16} />
          <span>{selectedTable?.name ?? "全部表"}</span>
        </div>

        {!selectedTable && <p>当前没有限定表，系统会在全部数据表中自动查找。</p>}

        {selectedTable && (
          <>
            <p>{selectedTable.description || "暂无说明"}</p>
            <div className="schema-meta-row">
              <span>{selectedTable.columns.length} columns</span>
              <span>{selectedTable.primary_keys.length} PK</span>
              <span>{selectedTable.foreign_keys.length} FK</span>
            </div>
            <div className="column-list full-column-list">
              {selectedTable.columns.map((column) => (
                <div className="column-item full-column-item" key={column.name}>
                  <div>
                    <span>{column.name}</span>
                    <p>{column.description || "暂无字段说明"}</p>
                  </div>
                  <strong>
                    {column.type}
                    {column.primary_key ? " PK" : ""}
                    {!column.nullable ? " NN" : ""}
                  </strong>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </aside>
  );
}

function tableClassName(tableName: string, selectedTableName: string, highlightedSet: Set<string>): string {
  const classes = ["table-item"];
  if (tableName === selectedTableName) classes.push("active");
  if (highlightedSet.has(tableName)) classes.push("highlighted");
  return classes.join(" ");
}
