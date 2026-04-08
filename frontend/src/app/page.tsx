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

interface IngestStatus {
  chunks_stored: number;
  pdf_files?: string[];
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

  const runIngestion = async () => {
    setIngesting(true);
    setError(null);
    setIngestResult(null);

    try {
      const res = await fetch(`${API_URL}/api/ingest?clear_existing=true`, {
        method: "POST",
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Ingestion failed");
      }

      const data: IngestResult = await res.json();
      setIngestResult(data);
      await loadIngestStatus();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Ingestion failed");
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
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc, i) => (
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
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Ingestion Pipeline */}
        <section className="mt-10">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                Ingestion Pipeline
              </h2>
              <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-1">
                Parse → Chunk → Embed → Store in vector database
              </p>
            </div>
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
