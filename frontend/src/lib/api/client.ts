/**
 * Core HTTP Client and Shared Utilities
 */
import type { DashboardFilters } from "./types";

const rawApiUrl = (process.env.NEXT_PUBLIC_API_URL || "").trim().replace(/\/+$/, "");

/**
 * Standardized API Base URL:
 * - When NEXT_PUBLIC_API_URL is configured to a valid HTTPS endpoint, browser calls it directly.
 * - When in browser over HTTPS and NEXT_PUBLIC_API_URL is HTTP (insecure), falls back to ""
 *   so requests route through the Next.js /api rewrite proxy without browser Mixed-Content rejection.
 * - When NEXT_PUBLIC_API_URL is empty/undefined, defaults to "" (using Next.js /api rewrite proxy).
 */
export const API_BASE_URL: string = (() => {
  if (typeof window !== "undefined" && window.location.protocol === "https:" && rawApiUrl.startsWith("http://")) {
    return "";
  }
  return rawApiUrl;
})();

/**
 * Robust API error reader that handles JSON error structures and plain text fallbacks.
 */
export async function readApiError(response: Response, defaultMessage: string = "Request failed"): Promise<string> {
  try {
    const err = await response.json();
    if (err?.detail) {
      if (typeof err.detail === "string") return err.detail;
      if (Array.isArray(err.detail)) {
        return err.detail.map((d: any) => d.msg || JSON.stringify(d)).join(", ");
      }
      return JSON.stringify(err.detail);
    }
    if (err?.message) return err.message;
    return defaultMessage;
  } catch {
    try {
      const text = await response.text();
      return text || defaultMessage;
    } catch {
      return defaultMessage;
    }
  }
}

/**
 * Parses raw error string into human-readable message.
 */
export function parseApiError(errorText: string, fallback: string): string {
  try {
    const parsed = JSON.parse(errorText);
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail)) {
      return parsed.detail.map((d: any) => d.msg || JSON.stringify(d)).join(", ");
    }
    if (parsed.message) return parsed.message;
    return fallback;
  } catch {
    return errorText || fallback;
  }
}

/**
 * Builds URL search parameters for dashboard filters.
 */
export function buildDashboardQuery(filters?: DashboardFilters): string {
  if (!filters) return "";
  const params = new URLSearchParams();
  if (filters.academic_session && filters.academic_session !== "all") params.set("academic_session", filters.academic_session);
  if (filters.campus && filters.campus !== "all") params.set("campus", filters.campus);
  if (filters.state && filters.state !== "all") params.set("state", filters.state);
  if (filters.source && filters.source !== "all") params.set("source", filters.source);
  if (filters.program && filters.program !== "all") params.set("program", filters.program);
  if (filters.years && filters.years.length > 0) params.set("years", filters.years.join(","));
  if (filters.from_date && filters.from_date.trim()) params.set("from_date", filters.from_date.trim());
  if (filters.to_date && filters.to_date.trim()) params.set("to_date", filters.to_date.trim());
  const str = params.toString();
  return str ? `?${str}` : "";
}

/**
 * Generic query parameter builder.
 */
export function buildQueryParams(params: Record<string, any>): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "" && value !== "all") {
      if (Array.isArray(value)) {
        if (value.length > 0) {
          searchParams.set(key, value.join(","));
        }
      } else {
        searchParams.set(key, String(value));
      }
    }
  }
  const str = searchParams.toString();
  return str ? `?${str}` : "";
}

/**
 * Shared HTTP request wrapper with standardized JSON handling and error extraction.
 */
export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit & { timeoutMs?: number } = {}
): Promise<T> {
  const url = endpoint.startsWith("http") ? endpoint : `${API_BASE_URL}${endpoint}`;
  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const timeoutMs = options.timeoutMs ?? 30000;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    controller.abort(new Error(`Request to ${endpoint} timed out after ${timeoutMs}ms`));
  }, timeoutMs);

  // Link caller signal if provided
  if (options.signal) {
    options.signal.addEventListener("abort", () => {
      clearTimeout(timeoutId);
      controller.abort();
    });
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
    });

    if (!response.ok) {
      const errorMsg = await readApiError(response, `Request failed with status ${response.status}`);
      throw new Error(errorMsg);
    }

    if (response.status === 204) {
      return {} as T;
    }

    return response.json();
  } finally {
    clearTimeout(timeoutId);
  }
}
