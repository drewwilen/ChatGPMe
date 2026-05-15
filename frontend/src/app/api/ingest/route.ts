import { getServerSession } from "next-auth";
import { NextResponse } from "next/server";
import { authOptions } from "@/lib/auth";

export async function POST(req: Request) {
  const session = await getServerSession(authOptions);

  if (!session?.accessToken) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { userId, maxFiles = 25, ownerOnly = true } = await req.json();

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
      return NextResponse.json(
        {
          error:
            (typeof data?.detail === "string" && data.detail) ||
            raw ||
            "Backend error",
        },
        { status: res.status }
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
