"use client";

import { signIn, signOut, useSession } from "next-auth/react";
import Image from "next/image";
import { useState } from "react";

interface IngestResult {
  documents_ingested: number;
  chunks_created: number;
}

export default function Home() {
  const { data: session, status } = useSession();
  const [maxFiles, setMaxFiles] = useState(50);
  const [ingesting, setIngesting] = useState(false);
  const [result, setResult] = useState<IngestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleIngest = async () => {
    if (!session?.user?.email) return;
    setIngesting(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch("/api/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          userId: session.user.email,
          maxFiles,
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Ingestion failed");
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIngesting(false);
    }
  };

  if (status === "loading") {
    return (
      <main style={styles.main}>
        <p style={{ color: "#888" }}>Loading…</p>
      </main>
    );
  }

  return (
    <main style={styles.main}>
      <div style={styles.card}>
        <h1 style={styles.title}>ChatGPMe</h1>
        <p style={styles.subtitle}>
          Connect your Google Drive to build a personalized writing model in
          your own voice.
        </p>

        {!session ? (
          <button style={styles.primaryBtn} onClick={() => signIn("google")}>
            Sign in with Google
          </button>
        ) : (
          <>
            {/* User info row */}
            <div style={styles.userRow}>
              {session.user?.image && (
                <Image
                  src={session.user.image}
                  alt="avatar"
                  width={40}
                  height={40}
                  style={{ borderRadius: "50%" }}
                />
              )}
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600 }}>{session.user?.name}</div>
                <div style={{ color: "#888", fontSize: 13 }}>
                  {session.user?.email}
                </div>
              </div>
              <button
                style={styles.ghostBtn}
                onClick={() => signOut()}
              >
                Sign out
              </button>
            </div>

            {/* Ingestion controls */}
            <div style={styles.section}>
              <label style={styles.label}>
                Max files to import
                <input
                  type="number"
                  min={1}
                  max={200}
                  value={maxFiles}
                  onChange={(e) => setMaxFiles(Number(e.target.value))}
                  style={styles.input}
                />
              </label>
              <p style={styles.hint}>
                We'll pull your most recently modified Google Docs (owner-only).
                Start with 50 and increase once everything works.
              </p>
            </div>

            <button
              style={{
                ...styles.primaryBtn,
                background: ingesting ? "#aaa" : "#1a73e8",
                cursor: ingesting ? "not-allowed" : "pointer",
              }}
              onClick={handleIngest}
              disabled={ingesting}
            >
              {ingesting
                ? `Ingesting your Drive… (this may take a minute)`
                : "Ingest My Google Drive"}
            </button>

            {result && (
              <div style={styles.successBox}>
                <strong>✓ Ingestion complete!</strong>
                <ul style={{ marginTop: 8, paddingLeft: 20 }}>
                  <li>Documents imported: {result.documents_ingested}</li>
                  <li>Text chunks created: {result.chunks_created}</li>
                </ul>
                <p style={{ marginTop: 8, fontSize: 13, color: "#2e7d32" }}>
                  Your corpus is ready. The model can now generate text in your
                  style.
                </p>
              </div>
            )}

            {error && (
              <div style={styles.errorBox}>
                <strong>Error:</strong> {error}
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  main: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "24px",
  },
  card: {
    background: "#fff",
    borderRadius: 12,
    padding: "40px 36px",
    maxWidth: 520,
    width: "100%",
    boxShadow: "0 2px 16px rgba(0,0,0,0.08)",
    display: "flex",
    flexDirection: "column",
    gap: 20,
  },
  title: {
    fontSize: 28,
    fontWeight: 700,
    letterSpacing: -0.5,
  },
  subtitle: {
    color: "#555",
    lineHeight: 1.5,
  },
  userRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "12px 16px",
    background: "#f4f6f8",
    borderRadius: 8,
  },
  section: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  label: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
    fontWeight: 600,
    fontSize: 14,
  },
  input: {
    padding: "8px 12px",
    border: "1px solid #ddd",
    borderRadius: 6,
    fontSize: 15,
    width: 100,
  },
  hint: {
    fontSize: 13,
    color: "#888",
    lineHeight: 1.5,
  },
  primaryBtn: {
    padding: "12px 20px",
    background: "#1a73e8",
    color: "#fff",
    border: "none",
    borderRadius: 8,
    fontSize: 15,
    fontWeight: 600,
    cursor: "pointer",
  },
  ghostBtn: {
    padding: "6px 12px",
    background: "transparent",
    color: "#555",
    border: "1px solid #ddd",
    borderRadius: 6,
    fontSize: 13,
    cursor: "pointer",
  },
  successBox: {
    padding: "16px",
    background: "#e8f5e9",
    borderRadius: 8,
    color: "#1b5e20",
  },
  errorBox: {
    padding: "16px",
    background: "#ffebee",
    borderRadius: 8,
    color: "#b71c1c",
  },
};
