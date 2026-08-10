/**
 * Thin typed wrapper around the Site Doctor FastAPI backend.
 *
 * Types here mirror models/schemas.py and the request/response models in
 * main.py exactly — if the backend schema changes, change it here too.
 */

/** Base URL of the API. Falls back to `/api`, which the Vite dev server
 *  proxies to http://127.0.0.1:8000 (see vite.config.ts). */
export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "/api";

// --- Schema mirrors --------------------------------------------------------

export type Category = "seo" | "accessibility" | "performance" | "security" | "ux";
export type Severity = "high" | "medium" | "low";
export type IssueSource = "lighthouse" | "security" | "ux";
export type CheckName = "seo" | "ux" | "security";

export interface Issue {
  id: string;
  category: Category;
  title: string;
  description: string;
  plain_language_summary: string | null;
  severity: Severity | null;
  fix_confidence: number | null;
  affected_selector: string | null;
  source_url: string | null;
  source: IssueSource;
  suggested_solution: string | null;
  solution_sources: string[];
}

export interface UXSuggestion {
  id: string;
  category: string;
  severity: Severity;
  observation: string;
  recommendation: string;
  page_url: string | null;
}

export interface AuditResult {
  url: string;
  scores: Partial<Record<Category, number>>; // 0–100
  issues: Issue[];
}

export interface AuditRequest {
  url: string;
  checks: CheckName[];
  max_depth: number;
  max_pages: number;
  security_confirmed: boolean;
  generate_report: boolean;
}

export interface AuditResponse {
  url: string;
  selected_checks: string[];
  pages_crawled: number;
  audit_before: AuditResult[];
  ux_suggestions: UXSuggestion[];
  security_findings: Issue[];
  triaged_issues: Issue[];
  report_available: boolean;
  report_download_url: string | null;
}

// --- Errors ----------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** FastAPI returns `{detail: string}` for HTTPException and
 *  `{detail: [{loc, msg, ...}]}` for 422 validation failures. */
function readDetail(body: unknown, fallback: string): string {
  if (typeof body !== "object" || body === null) return fallback;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (typeof d === "object" && d !== null ? (d as { msg?: string }).msg : null))
      .filter(Boolean);
    if (msgs.length) return msgs.join("; ");
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(
      `Can't reach the Site Doctor API at ${API_BASE_URL}. Check that the backend is running (uvicorn main:app --reload).`,
      null,
    );
  }

  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(
      readDetail(body, `The API returned ${response.status} ${response.statusText}.`),
      response.status,
    );
  }

  return (await response.json()) as T;
}

// --- Endpoints -------------------------------------------------------------

export function runAudit(payload: AuditRequest, signal?: AbortSignal) {
  return request<AuditResponse>("/audit", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export function checkHealth(signal?: AbortSignal) {
  return request<{ status: string }>("/health", { signal });
}

/** The backend hands back a root-relative path like `/reports/x.pdf`; make it
 *  absolute against whatever base the frontend is actually talking to. */
export function reportUrl(downloadPath: string): string {
  return `${API_BASE_URL}${downloadPath}`;
}

// --- Derived helpers -------------------------------------------------------

export const SEVERITY_ORDER: Severity[] = ["high", "medium", "low"];

/** Security findings are merged into `triaged_issues` by the graph, but be
 *  defensive: if a finding didn't make it through triage, still show it. */
export function collectIssues(response: AuditResponse): Issue[] {
  const byId = new Map<string, Issue>();
  for (const issue of [...response.triaged_issues, ...response.security_findings]) {
    if (!byId.has(issue.id)) byId.set(issue.id, issue);
  }
  const rank: Record<Severity | "none", number> = { high: 0, medium: 1, low: 2, none: 3 };
  return [...byId.values()].sort((a, b) => rank[a.severity ?? "none"] - rank[b.severity ?? "none"]);
}

export function countBySeverity(issues: Issue[]): Record<Severity, number> {
  return issues.reduce(
    (acc, issue) => {
      if (issue.severity) acc[issue.severity] += 1;
      return acc;
    },
    { high: 0, medium: 0, low: 0 } as Record<Severity, number>,
  );
}

/** Average each Lighthouse category across every page audited, so the summary
 *  reflects the whole crawl rather than only the entry URL. */
export function averageScores(results: AuditResult[]): Partial<Record<Category, number>> {
  const totals = new Map<Category, { sum: number; n: number }>();
  for (const result of results) {
    for (const [category, score] of Object.entries(result.scores)) {
      if (typeof score !== "number") continue;
      const entry = totals.get(category as Category) ?? { sum: 0, n: 0 };
      entry.sum += score;
      entry.n += 1;
      totals.set(category as Category, entry);
    }
  }
  const out: Partial<Record<Category, number>> = {};
  for (const [category, { sum, n }] of totals) out[category] = Math.round(sum / n);
  return out;
}
