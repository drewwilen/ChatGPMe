import { getServerSession } from "next-auth";
import { NextResponse } from "next/server";

import { authOptions } from "@/lib/auth";

export async function GET(req: Request) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { searchParams } = new URL(req.url);
  const bundleName = searchParams.get("bundleName");
  if (!bundleName) {
    return NextResponse.json({ error: "bundleName is required" }, { status: 400 });
  }

  const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";
  const target = `${backendUrl}/bundle/download/${encodeURIComponent(session.user.email)}/${encodeURIComponent(bundleName)}`;

  try {
    const res = await fetch(target);
    if (!res.ok) {
      const raw = await res.text();
      return NextResponse.json({ error: raw || "Backend error" }, { status: res.status });
    }

    const bytes = await res.arrayBuffer();
    return new NextResponse(bytes, {
      status: 200,
      headers: {
        "Content-Type": "application/zip",
        "Content-Disposition": `attachment; filename="${bundleName}.zip"`,
      },
    });
  } catch {
    return NextResponse.json(
      { error: `Could not reach backend at ${backendUrl}` },
      { status: 502 },
    );
  }
}
