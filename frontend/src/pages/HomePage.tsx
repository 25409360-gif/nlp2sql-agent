import { Database, MessageSquare, RefreshCw, Upload } from "lucide-react";
import { useEffect, useState } from "react";

import { getDatabaseHealth, getHealth, toApiClientError } from "../api/client";
import { ImportPage } from "./ImportPage";
import { QueryPage } from "./QueryPage";
import { TableBrowserPage } from "./TableBrowserPage";
import type { HealthResponse } from "../types/schema";
import type { StatusState } from "../types/status";

type PageKey = "query" | "tables" | "import";

const navigationItems: Array<{ key: PageKey; label: string }> = [
  { key: "query", label: "自然语言查询" },
  { key: "tables", label: "数据表浏览" },
  { key: "import", label: "文件上传导入" },
];

export function HomePage() {
  const [currentPage, setCurrentPage] = useState<PageKey>("query");
  const [backendStatus, setBackendStatus] = useState<StatusState>("idle");
  const [databaseStatus, setDatabaseStatus] = useState<StatusState>("idle");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [topbarError, setTopbarError] = useState("");
  const [queryRefreshSequence, setQueryRefreshSequence] = useState(0);
  const [tableBrowserRefreshSequence, setTableBrowserRefreshSequence] = useState(0);
  const [preferredTableName, setPreferredTableName] = useState("");

  async function loadShellStatus() {
    setTopbarError("");
    setBackendStatus("loading");
    setDatabaseStatus("loading");

    try {
      const [healthResult, databaseResult] = await Promise.all([getHealth(), getDatabaseHealth()]);
      setHealth(healthResult);
      setBackendStatus(healthResult.status === "ok" ? "ok" : "error");
      setDatabaseStatus(databaseResult.status === "ok" ? "ok" : "error");
    } catch (caught) {
      const apiError = toApiClientError(caught);
      setBackendStatus("error");
      setDatabaseStatus("error");
      setTopbarError(apiError.message);
    }
  }

  async function refreshPageData() {
    await loadShellStatus();
    setQueryRefreshSequence((current) => current + 1);
    setTableBrowserRefreshSequence((current) => current + 1);
  }

  function handleImportComplete(tableName: string) {
    setPreferredTableName(tableName);
    setTableBrowserRefreshSequence((current) => current + 1);
    setQueryRefreshSequence((current) => current + 1);
  }

  function openImportedTable(tableName: string) {
    setPreferredTableName(tableName);
    setTableBrowserRefreshSequence((current) => current + 1);
    setCurrentPage("tables");
  }

  function handleTablesDeleted(tableNames: string[]) {
    setPreferredTableName((current) => (tableNames.includes(current) ? "" : current));
    setQueryRefreshSequence((current) => current + 1);
    setTableBrowserRefreshSequence((current) => current + 1);
  }

  useEffect(() => {
    void loadShellStatus();
  }, []);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="topbar-left">
          <div className="brand-block">
            <h1>NLP2SQL Agent</h1>
            <p>Text-to-SQL Workbench</p>
          </div>

          <nav className="topbar-nav" aria-label="主导航">
            {navigationItems.map((item) => (
              <button
                aria-current={currentPage === item.key ? "page" : undefined}
                className={`nav-button ${currentPage === item.key ? "active" : ""}`}
                key={item.key}
                type="button"
                onClick={() => setCurrentPage(item.key)}
              >
                {navigationIcon(item.key)}
                <span>{item.label}</span>
              </button>
            ))}
          </nav>
        </div>

        <div className="topbar-status">
          <StatusPill label="API" status={backendStatus} value={health?.version ?? "-"} />
          <StatusPill label="DB" status={databaseStatus} value="PostgreSQL" />
          <button className="icon-button" type="button" onClick={() => void refreshPageData()} aria-label="刷新">
            <RefreshCw size={18} />
          </button>
        </div>
      </header>

      <section className="page-region" hidden={currentPage !== "query"}>
        <QueryPage
          backendStatus={backendStatus}
          databaseStatus={databaseStatus}
          health={health}
          refreshSignal={queryRefreshSequence}
          shellError={topbarError}
        />
      </section>
      <section className="page-region" hidden={currentPage !== "tables"}>
        <TableBrowserPage
          preferredTableName={preferredTableName}
          refreshSignal={tableBrowserRefreshSequence}
          onTablesDeleted={handleTablesDeleted}
        />
      </section>
      <section className="page-region" hidden={currentPage !== "import"}>
        <ImportPage onImportComplete={handleImportComplete} onViewImportedTable={openImportedTable} />
      </section>
    </main>
  );
}

function navigationIcon(page: PageKey) {
  if (page === "tables") return <Database size={16} />;
  if (page === "import") return <Upload size={16} />;
  return <MessageSquare size={16} />;
}

function StatusPill({ label, status, value }: { label: string; status: StatusState; value: string }) {
  return (
    <div className="status-pill">
      <span className={`status-dot ${status}`} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
