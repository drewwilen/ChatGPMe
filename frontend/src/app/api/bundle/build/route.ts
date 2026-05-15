import { getServerSession } from "next-auth";
import { NextResponse } from "next/server";

import { authOptions } from "@/lib/auth";

export async function POST(req: Request) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { bundleName } = await req.json().catch(() => ({}));
  const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

  try {
    const res = await fetch(`${backendUrl}/bundle/build`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: session.user.email,
        bundle_name: bundleName,
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
        { status: res.status },
      );
    }

    return NextResponse.json(data ?? {});
  } catch {
    return NextResponse.json(
      { error: `Could not reach backend at ${backendUrl}` },
      { status: 502 },
    );
  }
}
