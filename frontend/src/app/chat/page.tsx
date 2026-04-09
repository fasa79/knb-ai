"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Source {
  source: string;
  page: number;
  section: string;
  content_type: string;
  relevance_score: number;
  text_snippet: string;
}

interface QueryResponse {
  answer: string;
  sources: Source[];
  confidence: string;
  confidence_label: string;
  avg_score: number;
  intent: string;
  cached: boolean;
}

interface ModelInfo {
  id: string;
  name: string;
  rpm: number;
  rpd: number;
  provider: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  confidence?: string;
  confidenceLabel?: string;
  intent?: string;
  cached?: boolean;
}

const CONFIDENCE_COLORS: Record<string, string> = {
  high: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  medium:
    "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  low: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  none: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

const SUGGESTED_QUESTIONS = [
  "What was Khazanah's TWRR as of the latest reporting period?",
  "What were the key financial highlights for 2025?",
  "Summarise Khazanah's sustainability or ESG initiatives.",
  "What is Khazanah's total assets and realisable asset value?",
];

const COMPARE_QUESTIONS = [
  "How did Khazanah's total assets change from 2024 to 2025?",
  "Compare the TWRR performance between 2024 and 2025.",
];

/** Render answer text with proper markdown + [1], [2] citation badges. */
function FormattedAnswer({
  content,
  sources,
  onSourceClick,
}: {
  content: string;
  sources?: Source[];
  onSourceClick: (idx: number) => void;
}) {
  return (
    <div className="prose prose-sm dark:prose-invert max-w-none prose-table:text-sm prose-th:bg-zinc-100 dark:prose-th:bg-zinc-800 prose-th:px-3 prose-th:py-2 prose-td:px-3 prose-td:py-2 prose-th:text-left prose-table:border-collapse prose-th:border prose-td:border prose-th:border-zinc-300 dark:prose-th:border-zinc-600 prose-td:border-zinc-200 dark:prose-td:border-zinc-700">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Inject citation badges into text nodes
          p: ({ children }) => (
            <p>
              <CitationRenderer sources={sources} onSourceClick={onSourceClick}>
                {children}
              </CitationRenderer>
            </p>
          ),
          li: ({ children }) => (
            <li>
              <CitationRenderer sources={sources} onSourceClick={onSourceClick}>
                {children}
              </CitationRenderer>
            </li>
          ),
          td: ({ children }) => (
            <td>
              <CitationRenderer sources={sources} onSourceClick={onSourceClick}>
                {children}
              </CitationRenderer>
            </td>
          ),
          th: ({ children }) => (
            <th>
              <CitationRenderer sources={sources} onSourceClick={onSourceClick}>
                {children}
              </CitationRenderer>
            </th>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

/** Recursively process React children to replace [1], [2] text with citation badges. */
function CitationRenderer({
  children,
  sources,
  onSourceClick,
}: {
  children: React.ReactNode;
  sources?: Source[];
  onSourceClick: (idx: number) => void;
}) {
  return (
    <>
      {processChildren(children, sources, onSourceClick)}
    </>
  );
}

function processChildren(
  children: React.ReactNode,
  sources?: Source[],
  onSourceClick?: (idx: number) => void
): React.ReactNode {
  if (!children) return children;

  if (typeof children === "string") {
    return renderCitations(children, sources, onSourceClick);
  }

  if (Array.isArray(children)) {
    return children.map((child, i) => (
      <span key={i}>{processChildren(child, sources, onSourceClick)}</span>
    ));
  }

  return children;
}

function renderCitations(
  text: string,
  sources?: Source[],
  onSourceClick?: (idx: number) => void
): React.ReactNode {
  const parts = text.split(/(\[\d+\])/g);
  if (parts.length === 1) return text;

  return (
    <>
      {parts.map((part, k) => {
        const citMatch = part.match(/^\[(\d+)\]$/);
        if (citMatch) {
          const idx = parseInt(citMatch[1], 10) - 1;
          const isValid = sources && idx >= 0 && idx < sources.length;
          return (
            <button
              key={k}
              onClick={() => isValid && onSourceClick?.(idx)}
              className="inline-flex items-center justify-center ml-0.5 h-4 min-w-[16px] rounded bg-blue-100 px-1 text-[10px] font-bold text-blue-600 hover:bg-blue-200 align-super transition-colors dark:bg-blue-900/40 dark:text-blue-400 dark:hover:bg-blue-900/60"
              title={
                isValid
                  ? `${sources![idx].source} p.${sources![idx].page}`
                  : `Source ${citMatch[1]}`
              }
            >
              {citMatch[1]}
            </button>
          );
        }
        return <span key={k}>{part}</span>;
      })}
    </>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [expandedSource, setExpandedSource] = useState<number | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    fetch(`${API_URL}/api/models`)
      .then((r) => r.json())
      .then((data) => {
        setModels(data.models);
        setSelectedModel(data.default);
      })
      .catch(() => {});
  }, []);

  const sendQuery = async (question: string) => {
    if (!question.trim() || loading) return;

    const userMsg: Message = { role: "user", content: question };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, model: selectedModel || undefined }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Query failed");
      }

      const data: QueryResponse = await res.json();

      const assistantMsg: Message = {
        role: "assistant",
        content: data.answer,
        sources: data.sources,
        confidence: data.confidence,
        confidenceLabel: data.confidence_label,
        intent: data.intent,
        cached: data.cached,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: unknown) {
      const errorMsg: Message = {
        role: "assistant",
        content: `Error: ${err instanceof Error ? err.message : "Something went wrong"}`,
        confidence: "none",
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-zinc-50 dark:bg-zinc-950">
      {/* Header */}
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900 shrink-0">
        <div className="mx-auto max-w-5xl px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/" className="flex items-center gap-3 hover:opacity-80">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white font-bold text-sm">
                K
              </div>
              <div>
                <h1 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
                  Khazanah Annual Review AI
                </h1>
              </div>
            </Link>
          </div>
          <nav className="flex items-center gap-4 text-sm">
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="rounded-lg border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-xs text-zinc-700 focus:border-blue-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
            >
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({m.rpd} rpd)
                </option>
              ))}
            </select>
            <Link
              href="/"
              className="text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
            >
              Documents
            </Link>
            <Link
              href="/chat"
              className="text-blue-600 font-medium dark:text-blue-400"
            >
              Chat
            </Link>
            <Link
              href="/extract"
              className="text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
            >
              Extract
            </Link>
          </nav>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-6 py-6">
          {messages.length === 0 && (
            <div className="text-center py-16">
              <h2 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100 mb-3">
                Ask about the Annual Review
              </h2>
              <p className="text-zinc-500 dark:text-zinc-400 mb-8 max-w-md mx-auto">
                Ask questions about Khazanah&apos;s financial performance,
                portfolio, ESG initiatives, and more.
              </p>
              <p className="text-xs font-medium text-zinc-400 dark:text-zinc-500 uppercase tracking-wide mb-2">Search</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg mx-auto mb-6">
                {SUGGESTED_QUESTIONS.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => sendQuery(q)}
                    className="text-left px-4 py-3 rounded-xl border border-zinc-200 bg-white text-sm text-zinc-700 hover:border-blue-300 hover:bg-blue-50 transition-colors dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:border-blue-600 dark:hover:bg-blue-950/20"
                  >
                    {q}
                  </button>
                ))}
              </div>
              <p className="text-xs font-medium text-zinc-400 dark:text-zinc-500 uppercase tracking-wide mb-2">Compare</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg mx-auto">
                {COMPARE_QUESTIONS.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => sendQuery(q)}
                    className="text-left px-4 py-3 rounded-xl border border-green-200 bg-white text-sm text-zinc-700 hover:border-green-400 hover:bg-green-50 transition-colors dark:border-green-800 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:border-green-600 dark:hover:bg-green-950/20"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div
              key={i}
              className={`mb-6 ${msg.role === "user" ? "flex justify-end" : ""}`}
            >
              {msg.role === "user" ? (
                <div className="max-w-[80%] rounded-2xl rounded-br-md bg-blue-600 px-4 py-3 text-white">
                  {msg.content}
                </div>
              ) : (
                <div className="max-w-[90%]">
                  {/* Confidence badge */}
                  {msg.confidence && (
                    <div className="flex items-center gap-2 mb-2">
                      <span
                        className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${CONFIDENCE_COLORS[msg.confidence] || CONFIDENCE_COLORS.none}`}
                      >
                        {msg.confidence === "high" && "✓ "}
                        {msg.confidence === "medium" && "~ "}
                        {msg.confidence === "low" && "⚠ "}
                        {msg.confidence === "none" && "✗ "}
                        {msg.confidence} confidence
                      </span>
                      {msg.cached && (
                        <span className="text-xs text-zinc-400">cached</span>
                      )}
                      {msg.intent && msg.intent !== "search" && (
                        <span className="text-xs text-zinc-400">
                          [{msg.intent}]
                        </span>
                      )}
                    </div>
                  )}

                  {/* Answer */}
                  <div className="rounded-2xl rounded-bl-md bg-white border border-zinc-200 px-5 py-4 dark:bg-zinc-900 dark:border-zinc-800">
                    <div className="prose prose-sm dark:prose-invert max-w-none">
                      <FormattedAnswer
                        content={msg.content}
                        sources={msg.sources}
                        onSourceClick={(idx) =>
                          setExpandedSource(
                            expandedSource === i * 100 + idx
                              ? null
                              : i * 100 + idx
                          )
                        }
                      />
                    </div>
                  </div>

                  {/* Sources */}
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="mt-3 ml-1 flex flex-wrap gap-2">
                      {msg.sources.map((src, j) => {
                        const shortName = src.source
                          .replace(/\.pdf$/i, "")
                          .replace(/^KAR-\d{4}_/, "")
                          .replace(/-ENG$/, "")
                          .replace(/-/g, " ");
                        const isExpanded = expandedSource === i * 100 + j;
                        return (
                          <div key={j} className="relative">
                            <button
                              onClick={() =>
                                setExpandedSource(isExpanded ? null : i * 100 + j)
                              }
                              className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors ${
                                isExpanded
                                  ? "border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-600 dark:bg-blue-950/30 dark:text-blue-400"
                                  : "border-zinc-200 bg-zinc-50 text-zinc-600 hover:border-zinc-300 hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:border-zinc-600"
                              }`}
                            >
                              <span className="inline-flex items-center justify-center h-4 w-4 rounded bg-zinc-200 text-[10px] font-bold text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300">
                                {j + 1}
                              </span>
                              <span>{shortName}</span>
                              <span className="text-zinc-400 dark:text-zinc-500">
                                p.{src.page}
                              </span>
                            </button>
                            {isExpanded && (
                              <div className="absolute left-0 top-full mt-1 z-10 w-80 rounded-lg border border-zinc-200 bg-white p-3 shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
                                <div className="flex items-center justify-between mb-1.5">
                                  <span className="text-[10px] font-medium uppercase tracking-wider text-zinc-400">
                                    {src.content_type} · Page {src.page}
                                  </span>
                                </div>
                                <p className="text-xs leading-relaxed text-zinc-600 dark:text-zinc-300">
                                  {src.text_snippet}
                                </p>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="mb-6">
              <div className="flex items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
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
                Searching documents and generating answer...
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <div className="border-t border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900 shrink-0">
        <div className="mx-auto max-w-3xl px-6 py-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              sendQuery(input);
            }}
            className="flex gap-3"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about Khazanah's Annual Review..."
              className="flex-1 rounded-xl border border-zinc-300 bg-zinc-50 px-4 py-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-blue-400"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="rounded-xl bg-blue-600 px-5 py-3 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-zinc-300 disabled:cursor-not-allowed transition-colors dark:disabled:bg-zinc-700"
            >
              Send
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
