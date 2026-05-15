import { getServerSession } from "next-auth";
import { NextResponse } from "next/server";
import { authOptions } from "@/lib/auth";

function isGoogleAuthRefreshError(message: string) {
  const normalized = message.toLowerCase();
  return (
    normalized.includes("need to refresh the access token") ||
    normalized.includes("must specify refresh_token") ||
    normalized.includes("the credentials do not contain the necessary fields")
  );
}

export async function POST(req: Request) {
  const session = await getServerSession(authOptions);

  if (!session?.accessToken) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const {
    userId,
    maxFiles = 25,
    ownerOnly = true,
    fileIds = [],
  } = await req.json();

  if (!userId) {
    return NextResponse.json({ error: "userId is required" }, { status: 400 });
  }

  const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

  try {
    const res = await fetch(`${backendUrl}/ingest/gdrive`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        access_token: session.accessToken,
        max_files: maxFiles,
        owner_only: ownerOnly,
        file_ids: fileIds,
      }),
    });

    const raw = await res.text();
    let data: Record<string, unknown> | null = null;

    try {
      data = raw ? (JSON.parse(raw) as Record<string, unknown>) : null;
    } catch {
      data = null;
    }

    if (!res.ok) {
      const errorMessage =
        (typeof data?.detail === "string" && data.detail) ||
        raw ||
        "Backend error";
      return NextResponse.json(
        {
          error: errorMessage,
          authExpired: isGoogleAuthRefreshError(errorMessage),
        },
        { status: isGoogleAuthRefreshError(errorMessage) ? 401 : res.status }
      );
    }

    return NextResponse.json(data ?? {});
  } catch {
    return NextResponse.json(
      { error: `Could not reach ingestion backend at ${backendUrl}` },
      { status: 502 }
    );
  }
}
