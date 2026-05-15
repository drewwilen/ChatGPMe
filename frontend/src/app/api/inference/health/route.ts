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
  const { remoteUrl } = await req.json().catch(() => ({}));
  if (!remoteUrl || typeof remoteUrl !== "string") {
    return NextResponse.json({ error: "remoteUrl is required" }, { status: 400 });
  }

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
    const res = await fetch(`${baseUrl}/api/health`, {
      method: "GET",
      cache: "no-store",
    });
    const text = await res.text();
    let payload: Record<string, unknown> | null = null;
    try {
      payload = text ? (JSON.parse(text) as Record<string, unknown>) : null;
    } catch {
      payload = null;
    }

    if (!res.ok) {
      return NextResponse.json(
        { error: (payload?.error as string) || text || "Remote backend error" },
        { status: res.status },
      );
    }

    return NextResponse.json(payload ?? {});
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Could not reach remote inference server" },
      { status: 502 },
    );
  }
}
