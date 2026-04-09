"use client";

import { useState, useCallback, useEffect } from "react";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface UploadedFile {
  filename: string;
  size_kb: number;
}

interface DocumentInfo {
  filename: string;
  size_kb: number;
}

interface IngestResult {
  documents_processed: number;
  total_chunks_stored: number;
  total_duration_seconds: number;
  details: {
    filename: string;
    pages: number;
    chunks: number;
    tables: number;
    images: number;
    duration_s: number;
    status: string;
    error: string | null;
  }[];
}

interface FileIngestStatus {
  filename: string;
  chunks: number;
  ingested: boolean;
}

interface IngestStatus {
  chunks_stored: number;
  pdf_files?: string[];
  file_status?: FileIngestStatus[];
}

export default function Home() {
  const [recentUploads, setRecentUploads] = useState<UploadedFile[]>([]);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [uploading, setUploading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [ingestResult, setIngestResult] = useState<IngestResult | null>(null);
  const [ingestStatus, setIngestStatus] = useState<IngestStatus | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clearExisting, setClearExisting] = useState(true);
  const [useVision, setUseVision] = useState(false);

  const deleteDocument = async (filename: string) => {
    if (!confirm(`Delete ${filename}? This cannot be undone.`)) return;
    try {
      const res = await fetch(`${API_URL}/api/documents/${encodeURIComponent(filename)}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Delete failed");
      }
      await loadDocuments();
      await loadIngestStatus();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const loadDocuments = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/documents`);
      if (res.ok) {
        const data = await res.json();
        setDocuments(data.documents);
      }
    } catch {
      // Backend might not be running yet
    }
  }, []);

  const loadIngestStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/ingest/status`);
      if (res.ok) {
        const data = await res.json();
        setIngestStatus(data);
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    loadDocuments();
    loadIngestStatus();
  }, [loadDocuments, loadIngestStatus]);

  // Poll ingestion status while ingesting
  useEffect(() => {
    if (!ingesting) return;
    const interval = setInterval(async () => {
      await loadIngestStatus();
    }, 5000);
    return () => clearInterval(interval);
  }, [ingesting, loadIngestStatus]);

  const runIngestion = async () => {
    setIngesting(true);
    setError(null);
    setIngestResult(null);

    try {
      const params = new URLSearchParams();
      params.set("clear_existing", String(clearExisting));
      params.set("use_vision", String(useVision));

      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 300000); // 5 min timeout

      const res = await fetch(`${API_URL}/api/ingest?${params}`, {
        method: "POST",
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Ingestion failed");
      }

      const data: IngestResult = await res.json();
      setIngestResult(data);
      await loadIngestStatus();
    } catch (err: unknown) {
      // Ingestion may still succeed on the backend even if the fetch timed out
      // Refresh status after a short delay to check
      setTimeout(async () => {
        await loadIngestStatus();
        await loadDocuments();
      }, 3000);
      const msg = err instanceof Error ? err.message : "Ingestion failed";
      if (msg.includes("aborted") || msg.includes("Failed to fetch")) {
        setError("Request timed out, but ingestion may still be running. Status will refresh automatically.");
      } else {
        setError(msg);
      }
    } finally {
      setIngesting(false);
    }
  };

  const uploadFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are allowed");
      return;
    }

    setUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`${API_URL}/api/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Upload failed");
      }

      const data = await res.json();
      setRecentUploads((prev) => [...prev, data]);
      await loadDocuments();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const droppedFiles = Array.from(e.dataTransfer.files);
    droppedFiles.forEach((f) => uploadFile(f));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      Array.from(e.target.files).forEach((f) => uploadFile(f));
    }
  };

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      {/* Header */}
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto max-w-5xl px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-white font-bold text-sm">
              K
            </div>
            <div>
              <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                Khazanah Annual Review AI
              </h1>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                Upload &middot; Query &middot; Extract
              </p>
            </div>
          </div>
          <nav className="flex gap-4 text-sm">
            <Link href="/" className="text-blue-600 font-medium dark:text-blue-400">Documents</Link>
            <Link href="/chat" className="text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100">Chat</Link>
            <Link href="/extract" className="text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100">Extract</Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-10">
        {/* Upload Section */}
        <section>
          <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100 mb-4">
            Upload Documents
          </h2>

          {/* Drop Zone */}
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            className={`relative rounded-xl border-2 border-dashed p-12 text-center transition-colors ${
              dragOver
                ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30"
                : "border-zinc-300 bg-white hover:border-zinc-400 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:border-zinc-600"
            }`}
          >
            <input
              type="file"
              accept=".pdf"
              multiple
              onChange={handleFileSelect}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            />

            <div className="flex flex-col items-center gap-3">
              <svg
                className="h-10 w-10 text-zinc-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z"
                />
              </svg>
              <p className="text-zinc-600 dark:text-zinc-400">
                <span className="font-medium text-blue-600 dark:text-blue-400">
                  Click to upload
                </span>{" "}
                or drag and drop
              </p>
              <p className="text-sm text-zinc-400 dark:text-zinc-500">
                PDF files only &mdash; up to 100MB
              </p>
            </div>

            {uploading && (
              <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-white/80 dark:bg-zinc-900/80">
                <div className="flex items-center gap-3">
                  <svg
                    className="h-5 w-5 animate-spin text-blue-600"
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
                  <span className="font-medium text-zinc-700 dark:text-zinc-300">
                    Uploading...
                  </span>
                </div>
              </div>
            )}
          </div>

          {error && (
            <div className="mt-3 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-400">
              {error}
            </div>
          )}

          {/* Recent Uploads */}
          {recentUploads.length > 0 && (
            <div className="mt-4 space-y-2">
              {recentUploads.map((f, i) => (
                <div
                  key={i}
                  className="flex items-center gap-3 rounded-lg border border-green-200 bg-green-50 px-4 py-3 dark:border-green-800 dark:bg-green-950/30"
                >
                  <svg
                    className="h-5 w-5 text-green-600"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                  <span className="text-sm font-medium text-green-800 dark:text-green-300">
                    {f.filename}
                  </span>
                  <span className="text-xs text-green-600 dark:text-green-500">
                    {f.size_kb} KB
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Documents List */}
        <section className="mt-10">
          <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100 mb-4">
            Available Documents
          </h2>

          {documents.length === 0 ? (
            <p className="text-zinc-500 dark:text-zinc-400 text-sm">
              No documents uploaded yet.
            </p>
          ) : (
            <div className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-100 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/50">
                    <th className="px-4 py-3 text-left font-medium text-zinc-500 dark:text-zinc-400">
                      Filename
                    </th>
                    <th className="px-4 py-3 text-right font-medium text-zinc-500 dark:text-zinc-400">
                      Size
                    </th>
                    <th className="px-4 py-3 text-right font-medium text-zinc-500 dark:text-zinc-400">
                      Chunks
                    </th>
                    <th className="px-4 py-3 text-center font-medium text-zinc-500 dark:text-zinc-400">
                      Status
                    </th>
                    <th className="px-4 py-3 w-10"></th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc, i) => {
                    const fileStatus = ingestStatus?.file_status?.find(
                      (f) => f.filename === doc.filename
                    );
                    return (
                    <tr
                      key={i}
                      className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                    >
                      <td className="px-4 py-3 text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
                        <svg
                          className="h-4 w-4 text-red-500 shrink-0"
                          fill="currentColor"
                          viewBox="0 0 20 20"
                        >
                          <path d="M4 18h12a2 2 0 002-2V6.414A2 2 0 0017.414 5L14 1.586A2 2 0 0012.586 1H4a2 2 0 00-2 2v13a2 2 0 002 2z" />
                        </svg>
                        {doc.filename}
                      </td>
                      <td className="px-4 py-3 text-right text-zinc-500 dark:text-zinc-400">
                        {doc.size_kb > 1024
                          ? `${(doc.size_kb / 1024).toFixed(1)} MB`
                          : `${doc.size_kb} KB`}
                      </td>
                      <td className="px-4 py-3 text-right text-zinc-600 dark:text-zinc-400 tabular-nums">
                        {fileStatus ? fileStatus.chunks : "—"}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {fileStatus?.ingested ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
                            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                            </svg>
                            Ingested
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                            Pending
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={() => deleteDocument(doc.filename)}
                          className="text-zinc-400 hover:text-red-500 transition-colors"
                          title={`Delete ${doc.filename}`}
                        >
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Ingestion Pipeline */}
        <section className="mt-10">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                Ingestion Pipeline
              </h2>
              <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
                Parse → Chunk → Embed → Store in vector database
              </p>
            </div>
            <div className="flex flex-col items-end gap-3">
              <div className="flex items-center gap-4">
                {/* Toggles */}
                <label className="flex items-center gap-2 cursor-pointer" title="Clear all existing embeddings before ingesting. Turn off to append new documents to the existing knowledge base.">
                  <button
                    type="button"
                    role="switch"
                    aria-checked={clearExisting}
                    onClick={() => setClearExisting(!clearExisting)}
                    className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${
                      clearExisting ? "bg-blue-600" : "bg-zinc-300 dark:bg-zinc-600"
                    }`}
                  >
                    <span
                      className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
                        clearExisting ? "translate-x-4" : "translate-x-0.5"
                      }`}
                    />
                  </button>
                  <span className="text-xs text-zinc-600 dark:text-zinc-400 whitespace-nowrap">Clear existing</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer" title="Use Gemini Vision to analyze charts and infographics in PDFs. Slower and uses more API quota.">
                  <button
                    type="button"
                    role="switch"
                    aria-checked={useVision}
                    onClick={() => setUseVision(!useVision)}
                    className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${
                      useVision ? "bg-blue-600" : "bg-zinc-300 dark:bg-zinc-600"
                    }`}
                  >
                    <span
                      className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
                        useVision ? "translate-x-4" : "translate-x-0.5"
                      }`}
                    />
                  </button>
                  <span className="text-xs text-zinc-600 dark:text-zinc-400 whitespace-nowrap">Vision (charts)</span>
                </label>
              </div>
              {useVision && (
                <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/30 dark:border-amber-800 dark:text-amber-300 max-w-sm text-right">
                  <strong>Heads up:</strong> Vision analyzes each image via Gemini API. With free-tier rate limits (15 RPM), this can take <strong>several minutes</strong> per document and uses significant API quota.
                </div>
              )}
              <div className="flex items-center gap-3">
                {ingestStatus && (
                  <span className="text-sm text-zinc-500 dark:text-zinc-400">
                    {ingestStatus.chunks_stored} chunks stored
                  </span>
                )}
              <button
                onClick={runIngestion}
                disabled={ingesting || documents.length === 0}
                className={`rounded-lg px-5 py-2.5 text-sm font-medium transition-colors ${
                  ingesting || documents.length === 0
                    ? "bg-zinc-200 text-zinc-400 cursor-not-allowed dark:bg-zinc-800 dark:text-zinc-600"
                    : "bg-blue-600 text-white hover:bg-blue-700"
                }`}
              >
                {ingesting ? (
                  <span className="flex items-center gap-2">
                    <svg
                      className="h-4 w-4 animate-spin"
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
                    Processing...
                  </span>
                ) : (
                  "Run Ingestion"
                )}
              </button>
              </div>
            </div>
          </div>

          {/* Ingestion Results */}
          {ingestResult && (
            <div className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900 overflow-hidden">
              <div className="px-4 py-3 border-b border-zinc-100 dark:border-zinc-800 bg-green-50 dark:bg-green-950/20">
                <div className="flex items-center gap-2 text-sm font-medium text-green-800 dark:text-green-300">
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                  Pipeline complete — {ingestResult.total_chunks_stored} chunks stored in{" "}
                  {ingestResult.total_duration_seconds}s
                </div>
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-100 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/50">
                    <th className="px-4 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">Document</th>
                    <th className="px-4 py-2 text-right font-medium text-zinc-500 dark:text-zinc-400">Pages</th>
                    <th className="px-4 py-2 text-right font-medium text-zinc-500 dark:text-zinc-400">Chunks</th>
                    <th className="px-4 py-2 text-right font-medium text-zinc-500 dark:text-zinc-400">Tables</th>
                    <th className="px-4 py-2 text-right font-medium text-zinc-500 dark:text-zinc-400">Time</th>
                    <th className="px-4 py-2 text-right font-medium text-zinc-500 dark:text-zinc-400">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {ingestResult.details.map((d, i) => (
                    <tr key={i} className="border-b border-zinc-100 last:border-0 dark:border-zinc-800">
                      <td className="px-4 py-2 text-zinc-900 dark:text-zinc-100">{d.filename}</td>
                      <td className="px-4 py-2 text-right text-zinc-600 dark:text-zinc-400">{d.pages}</td>
                      <td className="px-4 py-2 text-right text-zinc-600 dark:text-zinc-400">{d.chunks}</td>
                      <td className="px-4 py-2 text-right text-zinc-600 dark:text-zinc-400">{d.tables}</td>
                      <td className="px-4 py-2 text-right text-zinc-600 dark:text-zinc-400">{d.duration_s}s</td>
                      <td className="px-4 py-2 text-right">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                            d.status === "success"
                              ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                              : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                          }`}
                        >
                          {d.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
