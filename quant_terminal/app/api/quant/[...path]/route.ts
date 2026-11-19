import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ALLOWED_ENDPOINTS = new Set([
  "health",
  "markets",
  "scanner/candidates",
  "research/experiments",
  "backtests",
  "paper/positions",
  "paper/history",
  "risk/summary"
]);

function jsonUnavailable(reason: string, status = 503) {
  return NextResponse.json(
    { status: "unavailable", reason, as_of: new Date().toISOString() },
    { status, headers: { "Cache-Control": "no-store" } }
  );
}

function isLoopback(hostname: string) {
  const host = hostname.replace(/^\[|\]$/g, "").toLowerCase();
  return host === "localhost" || host === "127.0.0.1" || host === "::1";
}

function upstreamBase() {
  const raw = process.env.QUANT_API_BASE_URL || "http://127.0.0.1:8000";
  const token = process.env.QUANT_API_TOKEN || "";

  let base: URL;
  try {
    base = new URL(raw);
  } catch {
    throw new Error("invalid_api_base_url");
  }

  if (
    !["http:", "https:"].includes(base.protocol) ||
    base.username ||
    base.password ||
    base.search ||
    base.hash ||
    (base.pathname !== "/" && base.pathname !== "")
  ) {
    throw new Error("invalid_api_base_url");
  }

  if (!token && !isLoopback(base.hostname)) {
    throw new Error("remote_api_requires_server_token");
  }
  if (token && !isLoopback(base.hostname) && base.protocol !== "https:") {
    throw new Error("remote_api_requires_https");
  }

  return { base, token };
}

function safeQuery(request: NextRequest, endpoint: string) {
  const incoming = request.nextUrl.searchParams;
  const output = new URLSearchParams();

  if (endpoint === "markets") {
    const symbols = incoming.get("symbols");
    if (symbols !== null) {
      if (!/^[A-Z0-9,]+$/.test(symbols)) throw new Error("invalid_symbols");
      output.set("symbols", symbols);
    }
  } else if (
    ["scanner/candidates", "research/experiments", "backtests", "paper/history"].includes(endpoint)
  ) {
    const limit = incoming.get("limit");
    if (limit !== null) {
      const parsed = Number(limit);
      const maximum = endpoint === "paper/history" ? 500 : 200;
      if (!Number.isInteger(parsed) || parsed < 1 || parsed > maximum) {
        throw new Error("invalid_limit");
      }
      output.set("limit", String(parsed));
    }
  }

  for (const key of incoming.keys()) {
    const allowed = endpoint === "markets" ? key === "symbols" :
      ["scanner/candidates", "research/experiments", "backtests", "paper/history"].includes(endpoint) && key === "limit";
    if (!allowed) throw new Error("unsupported_query_parameter");
  }
  return output;
}

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const endpoint = Array.isArray(path) ? path.join("/") : "";

  if (!ALLOWED_ENDPOINTS.has(endpoint)) {
    return jsonUnavailable("endpoint_not_allowed", 404);
  }

  let base: URL;
  let token: string;
  let query: URLSearchParams;
  try {
    const config = upstreamBase();
    base = config.base;
    token = config.token;
    query = safeQuery(request, endpoint);
  } catch (error) {
    const reason = error instanceof Error ? error.message : "invalid_proxy_configuration";
    return jsonUnavailable(reason, 503);
  }

  const target = new URL(`/api/v1/${endpoint}`, base);
  target.search = query.toString();

  try {
    const response = await fetch(target, {
      method: "GET",
      headers: {
        Accept: "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(10_000)
    });

    const contentType = response.headers.get("content-type") || "";
    if (!contentType.toLowerCase().includes("application/json")) {
      return jsonUnavailable("upstream_non_json_response", 502);
    }

    const body = await response.text();
    return new Response(body, {
      status: response.status,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff"
      }
    });
  } catch {
    return jsonUnavailable("read_only_api_unreachable", 503);
  }
}
