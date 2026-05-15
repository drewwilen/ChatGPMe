import { NextResponse } from "next/server";

function normalizeRemoteUrl(value: string): string {
  return value.trim().replace(/\/+$/, "");
}

function parseRemoteUrl(value: string): URL {
  let parsed: URL;
  try {
    parsed = new URL(normalizeRemoteUrl(value));
  } catch {
    throw new Error("remoteUrl must be a valid http or https URL");
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("remoteUrl must use http or https");
  }

  return parsed;
}

export async function POST(req: Request) {
  const payload = await req.json().catch(() => null);
  if (!payload || typeof payload !== "object") {
    return NextResponse.json({ error: "Invalid JSON payload" }, { status: 400 });
  }

  const remoteUrl = typeof payload.remoteUrl === "string" ? payload.remoteUrl : "";
  if (!remoteUrl) {
    return NextResponse.json({ error: "remoteUrl is required" }, { status: 400 });
  }
  if (typeof payload.mode !== "string" || !payload.mode.trim()) {
    return NextResponse.json({ error: "mode is required" }, { status: 400 });
  }

  const body = {
    text: payload.text ?? "",
    mode: payload.mode,
    max_new_tokens: payload.max_new_tokens ?? 80,
    temperature: payload.temperature ?? 0.7,
    top_p: payload.top_p ?? 0.95,
  };

  let baseUrl: string;
  try {
    baseUrl = parseRemoteUrl(remoteUrl).toString().replace(/\/+$/, "");
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Invalid remoteUrl" },
      { status: 400 },
    );
  }

  try {
    const res = await fetch(`${baseUrl}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    let parsed: Record<string, unknown> | null = null;
    try {
      parsed = text ? (JSON.parse(text) as Record<string, unknown>) : null;
    } catch {
      parsed = null;
    }

    if (!res.ok) {
      return NextResponse.json(
        { error: (parsed?.error as string) || text || "Remote backend error" },
        { status: res.status },
      );
    }

    return NextResponse.json(parsed ?? {});
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Could not reach remote inference server" },
      { status: 502 },
    );
  }
}
