"use client";

import { useState } from "react";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ExtractionResult {
  extraction_type: string;
  data: Record<string, unknown> | null;
  chunks_used?: number;
  sources?: { source: string; page: number; content_type: string }[];
  error?: string;
  errors?: string[];
  fallback?: boolean;
}

interface PortfolioCompany {
  name: string;
  sector: string | null;
  ownership_pct: number | null;
  asset_class: string | null;
  description: string | null;
}

interface FinancialMetric {
  metric_name: string;
  value: string;
  year: string | null;
  unit: string | null;
  source_context: string | null;
}

interface AssetClassPerformance {
  asset_class: string;
  portfolio_weight_pct: number | null;
  twrr_latest: string | null;
  twrr_rolling: string | null;
  yearly_returns: Record<string, string> | null;
  role: string | null;
}

interface KeyHighlight {
  category: string;
  title: string;
  description: string;
  value: string | null;
  year: string | null;
}

const EXTRACTION_TYPES = [
  { id: "all", label: "All Data", description: "Extract everything at once" },
  {
    id: "portfolio",
    label: "Portfolio Companies",
    description: "Companies, sectors, ownership stakes",
  },
  {
    id: "financials",
    label: "Financial Metrics",
    description: "RAV, TWRR, assets, dividends",
  },
  {
    id: "investment_performance",
    label: "Investment Performance",
    description: "Returns by asset class",
  },
  {
    id: "highlights",
    label: "Key Highlights",
    description: "Strategic initiatives & milestones",
  },
  {
    id: "custom",
    label: "Custom Query",
    description: "Extract anything you define",
  },
];

function DataTable({
  headers,
  rows,
}: {
  headers: string[];
  rows: (string | number | null)[][];
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
      <table className="min-w-full text-sm">
        <thead className="bg-gray-50 dark:bg-gray-800">
          <tr>
            {headers.map((h) => (
              <th
                key={h}
                className="px-4 py-3 text-left font-semibold text-gray-700 dark:text-gray-300"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
          {rows.map((row, i) => (
            <tr
              key={i}
              className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
            >
              {row.map((cell, j) => (
                <td
                  key={j}
                  className="px-4 py-3 text-gray-800 dark:text-gray-200"
                >
                  {cell ?? (
                    <span className="text-gray-400 italic text-xs">N/A</span>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PortfolioTable({ data }: { data: { companies: PortfolioCompany[] } }) {
  if (!data.companies?.length) return <EmptyState type="portfolio companies" />;
  return (
    <DataTable
      headers={["Company", "Sector", "Ownership %", "Asset Class", "Description"]}
      rows={data.companies.map((c) => [
        c.name,
        c.sector,
        c.ownership_pct != null ? `${c.ownership_pct}%` : null,
        c.asset_class,
        c.description,
      ])}
    />
  );
}

function FinancialsTable({
  data,
}: {
  data: { metrics: FinancialMetric[] };
}) {
  if (!data.metrics?.length) return <EmptyState type="financial metrics" />;
  return (
    <DataTable
      headers={["Metric", "Value", "Year", "Unit", "Context"]}
      rows={data.metrics.map((m) => [
        m.metric_name,
        m.value,
        m.year,
        m.unit,
        m.source_context,
      ])}
    />
  );
}

function InvestmentTable({
  data,
}: {
  data: { asset_classes: AssetClassPerformance[] };
}) {
  if (!data.asset_classes?.length)
    return <EmptyState type="investment performance" />;
  return (
    <DataTable
      headers={[
        "Asset Class",
        "Weight %",
        "Latest TWRR",
        "Rolling TWRR",
        "Role",
      ]}
      rows={data.asset_classes.map((a) => [
        a.asset_class,
        a.portfolio_weight_pct != null ? `${a.portfolio_weight_pct}%` : null,
        a.twrr_latest,
        a.twrr_rolling,
        a.role,
      ])}
    />
  );
}

function HighlightsTable({
  data,
}: {
  data: { highlights: KeyHighlight[] };
}) {
  if (!data.highlights?.length)
    return <EmptyState type="highlights" />;
  return (
    <DataTable
      headers={["Category", "Title", "Description", "Value", "Year"]}
      rows={data.highlights.map((h) => [
        h.category,
        h.title,
        h.description,
        h.value,
        h.year,
      ])}
    />
  );
}

function CustomTable({ data }: { data: { items: { field_name: string; value: string; source_context: string | null }[] } }) {
  if (!data.items?.length) return <EmptyState type="custom data" />;
  return (
    <DataTable
      headers={["Field", "Value", "Source"]}
      rows={data.items.map((item) => [item.field_name, item.value, item.source_context])}
    />
  );
}

function EmptyState({ type }: { type: string }) {
  return (
    <div className="text-center py-8 text-gray-500 dark:text-gray-400">
      <p>No {type} found in the extracted data.</p>
    </div>
  );
}

function renderExtractionData(type: string, data: Record<string, unknown>) {
  if (type === "all") {
    const sections: React.ReactNode[] = [];
    const allData = data as Record<string, Record<string, unknown>>;

    if (allData.portfolio)
      sections.push(
        <div key="p" className="space-y-2">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
            Portfolio Companies
          </h3>
          <PortfolioTable data={allData.portfolio as { companies: PortfolioCompany[] }} />
        </div>
      );
    if (allData.financials)
      sections.push(
        <div key="f" className="space-y-2">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
            Financial Metrics
          </h3>
          <FinancialsTable data={allData.financials as { metrics: FinancialMetric[] }} />
        </div>
      );
    if (allData.investment_performance)
      sections.push(
        <div key="i" className="space-y-2">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
            Investment Performance
          </h3>
          <InvestmentTable
            data={allData.investment_performance as { asset_classes: AssetClassPerformance[] }}
          />
        </div>
      );
    if (allData.highlights)
      sections.push(
        <div key="h" className="space-y-2">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
            Key Highlights
          </h3>
          <HighlightsTable data={allData.highlights as { highlights: KeyHighlight[] }} />
        </div>
      );

    if (sections.length === 0) return <EmptyState type="data" />;
    return <div className="space-y-6">{sections}</div>;
  }

  switch (type) {
    case "portfolio":
      return <PortfolioTable data={data as { companies: PortfolioCompany[] }} />;
    case "financials":
      return <FinancialsTable data={data as { metrics: FinancialMetric[] }} />;
    case "investment_performance":
      return <InvestmentTable data={data as { asset_classes: AssetClassPerformance[] }} />;
    case "highlights":
      return <HighlightsTable data={data as { highlights: KeyHighlight[] }} />;
    case "custom":
      return <CustomTable data={data as { items: { field_name: string; value: string; source_context: string | null }[] }} />;
    default:
      return (
        <pre className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 text-sm overflow-x-auto">
          {JSON.stringify(data, null, 2)}
        </pre>
      );
  }
}

export default function ExtractPage() {
  const [selectedType, setSelectedType] = useState("all");
  const [customQuery, setCustomQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ExtractionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState<number | null>(null);

  const runExtraction = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setElapsed(null);
    const start = Date.now();

    try {
      const body: Record<string, string> = { extraction_type: selectedType };
      if (selectedType === "custom" && customQuery.trim()) {
        body.query = customQuery.trim();
      }

      const res = await fetch(`${API_URL}/api/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data: ExtractionResult = await res.json();
      setResult(data);
      setElapsed(Math.round((Date.now() - start) / 1000));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction failed");
    } finally {
      setLoading(false);
    }
  };

  const exportJSON = () => {
    if (!result?.data) return;
    const blob = new Blob([JSON.stringify(result.data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `khazanah_${result.extraction_type}_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <main className="min-h-screen bg-gray-50 dark:bg-gray-950">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md border-b border-gray-200 dark:border-gray-800">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-gray-900 dark:text-white">
              Structured Data Extraction
            </h1>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Extract portfolio, financials, and insights from the Annual Review
            </p>
          </div>
          <nav className="flex gap-2">
            <Link
              href="/"
              className="px-3 py-1.5 text-sm rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400 transition-colors"
            >
              Documents
            </Link>
            <Link
              href="/chat"
              className="px-3 py-1.5 text-sm rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400 transition-colors"
            >
              Chat
            </Link>
            <span className="px-3 py-1.5 text-sm bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400 rounded-lg font-medium">
              Extract
            </span>
          </nav>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
        {/* Extraction Type Selector */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {EXTRACTION_TYPES.map((t) => (
            <button
              key={t.id}
              onClick={() => setSelectedType(t.id)}
              className={`p-3 rounded-xl border text-left transition-all ${
                selectedType === t.id
                  ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20 ring-1 ring-blue-500"
                  : "border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 bg-white dark:bg-gray-900"
              }`}
            >
              <div className="font-medium text-sm text-gray-900 dark:text-white">
                {t.label}
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                {t.description}
              </div>
            </button>
          ))}
        </div>

        {/* Custom Query Input */}
        {selectedType === "custom" && (
          <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              What would you like to extract?
            </label>
            <input
              type="text"
              value={customQuery}
              onChange={(e) => setCustomQuery(e.target.value)}
              placeholder='e.g. "Extract all ESG initiatives with dates and amounts"'
              className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              onKeyDown={(e) => e.key === "Enter" && runExtraction()}
            />
          </div>
        )}

        {/* Run Button */}
        <div className="flex items-center gap-4">
          <button
            onClick={runExtraction}
            disabled={loading || (selectedType === "custom" && !customQuery.trim())}
            className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded-xl font-medium transition-colors flex items-center gap-2"
          >
            {loading ? (
              <>
                <svg
                  className="animate-spin h-4 w-4"
                  viewBox="0 0 24 24"
                  fill="none"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
                Extracting...
              </>
            ) : (
              "Run Extraction"
            )}
          </button>

          {result?.data && (
            <button
              onClick={exportJSON}
              className="px-4 py-2.5 border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-xl text-sm text-gray-700 dark:text-gray-300 transition-colors"
            >
              Export JSON
            </button>
          )}

          {elapsed !== null && (
            <span className="text-sm text-gray-500 dark:text-gray-400">
              Completed in {elapsed}s
              {result?.chunks_used && ` · ${result.chunks_used} chunks used`}
              {result?.fallback && (
                <span className="text-yellow-600 dark:text-yellow-400 ml-1">
                  (fallback mode)
                </span>
              )}
            </span>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 text-red-700 dark:text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Results */}
        {result?.data && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                Extracted Data
              </h2>
              {result.sources && result.sources.length > 0 && (
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  Sources:{" "}
                  {[...new Set(result.sources.map((s) => s.source))].join(", ")}
                </span>
              )}
            </div>
            {renderExtractionData(
              result.extraction_type,
              result.data as Record<string, unknown>
            )}
          </div>
        )}

        {result && !result.data && result.error && (
          <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-xl p-4 text-yellow-700 dark:text-yellow-400 text-sm">
            {result.error}
          </div>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div className="space-y-4 animate-pulse">
            <div className="h-6 bg-gray-200 dark:bg-gray-800 rounded w-1/4" />
            <div className="h-64 bg-gray-200 dark:bg-gray-800 rounded-xl" />
          </div>
        )}
      </div>
    </main>
  );
}
