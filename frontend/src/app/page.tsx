"use client";

import Image from "next/image";
import { signIn, signOut, useSession } from "next-auth/react";
import { useEffect, useRef, useState } from "react";

type SourceMode = "recent" | "selection";
type TabId = "directions" | "setup" | "inference" | "editor" | "assistant";

interface DriveFile {
  id: string;
  name: string;
  mime_type: string;
  modified_time: string | null;
}

interface IngestResult {
  documents_ingested: number;
  chunks_created: number;
}

interface UserStatePayload {
  has_corpus: boolean;
  documents_ingested: number;
  chunks_created: number;
  style_train_rows: number;
  available_bundles: Array<{ name: string; size_bytes: number }>;
}

interface BundleBuildResult {
  bundle_name: string;
  dataset_rows: number;
  adapter_dir_name: string;
}

interface BackendHealth {
  status?: string;
  backend?: {
    ready?: boolean;
    loaded?: boolean;
    adapter_exists?: boolean;
    error?: string | null;
    model_name?: string;
    remote_url?: string;
  };
}

interface SetupStep {
  id: string;
  label: string;
  detail: string;
  done: boolean;
  tab: TabId;
}

interface EditorSelectionState {
  start: number;
  end: number;
  text: string;
}

interface SelectionComment {
  selection: string;
  comment: string;
}

const REMOTE_URL_STORAGE_KEY = "chatgpme.remoteUrl";

export default function Home() {
  const { data: session, status } = useSession();

  const [activeTab, setActiveTab] = useState<TabId>("directions");
  const [sourceMode, setSourceMode] = useState<SourceMode>("recent");
  const [maxFiles, setMaxFiles] = useState(25);
  const [ownerOnly, setOwnerOnly] = useState(true);

  const [driveFiles, setDriveFiles] = useState<DriveFile[]>([]);
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [driveSearch, setDriveSearch] = useState("");
  const [listingFiles, setListingFiles] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [buildingBundle, setBuildingBundle] = useState(false);
  const [setupMessage, setSetupMessage] = useState<string | null>(null);
  const [setupError, setSetupError] = useState<string | null>(null);

  const [ingestResult, setIngestResult] = useState<IngestResult | null>(null);
  const [userState, setUserState] = useState<UserStatePayload | null>(null);
  const [bundleResult, setBundleResult] = useState<BundleBuildResult | null>(null);

  const [remoteUrlInput, setRemoteUrlInput] = useState("");
  const [verifiedRemoteUrl, setVerifiedRemoteUrl] = useState("");
  const [healthPayload, setHealthPayload] = useState<BackendHealth | null>(null);
  const [testingRemote, setTestingRemote] = useState(false);
  const [remoteError, setRemoteError] = useState<string | null>(null);

  const [editorInput, setEditorInput] = useState("");
  const [currentSuggestion, setCurrentSuggestion] = useState("");
  const [editorMeta, setEditorMeta] = useState("Idle");
  const [editorSelection, setEditorSelection] = useState<EditorSelectionState | null>(null);
  const [commentInstruction, setCommentInstruction] = useState("");
  const [selectionComment, setSelectionComment] = useState<SelectionComment | null>(null);
  const [selectionCommentMeta, setSelectionCommentMeta] = useState(
    "Highlight text in the editor to generate a margin comment.",
  );
  const [assistantMode, setAssistantMode] = useState("assistant_draft");
  const [assistantInput, setAssistantInput] = useState("");
  const [assistantOutput, setAssistantOutput] = useState("");
  const [assistantMeta, setAssistantMeta] = useState("No generation yet");
  const editorRequestIdRef = useRef(0);
  const editorInputRef = useRef<HTMLTextAreaElement | null>(null);
  const editorGhostRef = useRef<HTMLPreElement | null>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem(REMOTE_URL_STORAGE_KEY);
    if (!stored) {
      return;
    }

    setRemoteUrlInput(stored);
    void testRemote(stored, false);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("reauth") === "drive") {
      setSetupError("Google Drive access expired. Sign in with Google again to refresh permissions.");
      params.delete("reauth");
      const next = params.toString();
      window.history.replaceState({}, "", next ? `/?${next}` : "/");
    }
  }, []);

  useEffect(() => {
    if (status === "authenticated" && session?.user?.email) {
      void refreshUserState();
    }
  }, [status, session?.user?.email]);

  useEffect(() => {
    if (status !== "authenticated" || !session?.user?.email) {
      return;
    }

    const timeoutId = setTimeout(() => {
      void loadDriveFiles(false);
    }, 250);

    return () => clearTimeout(timeoutId);
  }, [status, session?.user?.email, maxFiles, ownerOnly]);

  async function refreshUserState() {
    const res = await fetch("/api/user-state", { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error ?? "Could not load user state");
    }
    setUserState(data);
  }

  async function loadDriveFiles(showSuccessMessage = true) {
    setListingFiles(true);
    setSetupError(null);
    try {
      const res = await fetch("/api/drive-files", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ maxFiles, ownerOnly }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (data.authExpired) {
          await handleExpiredGoogleSession(
            "Google Drive access expired. Sign in again to refresh permissions.",
          );
          return;
        }
        throw new Error(data.error ?? "Could not load Google Drive files");
      }
      const files = (data.files as DriveFile[]) ?? [];
      setDriveFiles(files);
      setSelectedFileIds((current) =>
        current.filter((id) => files.some((file) => file.id === id)),
      );
      if (showSuccessMessage) {
        setSetupMessage(`Loaded ${files.length} files from Google Drive.`);
      }
    } catch (error) {
      setSetupError(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setListingFiles(false);
    }
  }

  function toggleSelectedFile(fileId: string) {
    setSelectedFileIds((current) =>
      current.includes(fileId)
        ? current.filter((id) => id !== fileId)
        : [...current, fileId],
    );
  }

  function selectAllVisibleFiles(fileIds: string[]) {
    setSelectedFileIds((current) => Array.from(new Set([...current, ...fileIds])));
  }

  function clearVisibleFiles(fileIds: string[]) {
    setSelectedFileIds((current) => current.filter((id) => !fileIds.includes(id)));
  }

  async function handleIngest() {
    if (!session?.user?.email) {
      return;
    }
    if (sourceMode === "selection" && selectedFileIds.length === 0) {
      setSetupError("Select at least one Google Doc before ingesting.");
      return;
    }

    setIngesting(true);
    setSetupError(null);
    setSetupMessage(null);
    setIngestResult(null);
    try {
      const res = await fetch("/api/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          userId: session.user.email,
          maxFiles,
          ownerOnly,
          fileIds: sourceMode === "selection" ? selectedFileIds : [],
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (data.authExpired) {
          await handleExpiredGoogleSession(
            "Google Drive access expired while ingesting. Sign in again and retry.",
          );
          return;
        }
        throw new Error(data.error ?? "Ingestion failed");
      }
      setIngestResult(data);
      setSetupMessage("Corpus ingested and style training data is ready.");
      await refreshUserState();
    } catch (error) {
      setSetupError(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setIngesting(false);
    }
  }

  async function handleBuildBundle() {
    setBuildingBundle(true);
    setSetupError(null);
    setSetupMessage(null);
    try {
      const res = await fetch("/api/bundle/build", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error ?? "Bundle build failed");
      }
      setBundleResult(data);
      setSetupMessage(
        "Colab bundle generated. Download it and run the included notebook in Colab.",
      );
      await refreshUserState();
    } catch (error) {
      setSetupError(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setBuildingBundle(false);
    }
  }

  async function testRemote(urlToTest = remoteUrlInput, persistOnSuccess = true) {
    const normalizedUrl = normalizeRemoteUrl(urlToTest);
    if (!normalizedUrl) {
      setRemoteError("Paste your ngrok URL first.");
      setVerifiedRemoteUrl("");
      setHealthPayload(null);
      return;
    }

    setTestingRemote(true);
    setRemoteError(null);
    try {
      const res = await fetch("/api/inference/health", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ remoteUrl: normalizedUrl }),
      });
      const data = (await res.json()) as BackendHealth & { error?: string };
      if (!res.ok) {
        throw new Error(data.error ?? "Health check failed");
      }

      const validationError = getRemoteHealthError(data);
      if (validationError) {
        throw new Error(validationError);
      }

      setRemoteUrlInput(normalizedUrl);
      setVerifiedRemoteUrl(normalizedUrl);
      setHealthPayload(data);
      if (persistOnSuccess) {
        window.localStorage.setItem(REMOTE_URL_STORAGE_KEY, normalizedUrl);
      }
    } catch (error) {
      setHealthPayload(null);
      setVerifiedRemoteUrl("");
      window.localStorage.removeItem(REMOTE_URL_STORAGE_KEY);
      setRemoteError(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setTestingRemote(false);
    }
  }

  async function generateRemote(payload: {
    text: string;
    mode: string;
    max_new_tokens: number;
    temperature: number;
    top_p: number;
  }) {
    const healthError = getRemoteHealthError(healthPayload);
    if (!verifiedRemoteUrl) {
      throw new Error("Connect and verify a remote inference URL first.");
    }
    if (healthError) {
      throw new Error(healthError);
    }

    const res = await fetch("/api/inference/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        remoteUrl: verifiedRemoteUrl,
        ...payload,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error ?? "Generation failed");
    }
    return data as { completion?: string; latency_ms?: number };
  }

  async function requestEditorSuggestion() {
    const requestId = ++editorRequestIdRef.current;
    if (editorInput.trim().length < 20) {
      setCurrentSuggestion("");
      setEditorMeta("Add a bit more text to get a continuation.");
      return;
    }
    setEditorMeta("Generating suggestion...");
    try {
      const payload = await generateRemote({
        text: editorInput,
        mode: "editor_continue",
        max_new_tokens: 24,
        temperature: 0.45,
        top_p: 0.95,
      });
      const suggestion = shortenSuggestion(payload.completion ?? "");
      if (requestId !== editorRequestIdRef.current) {
        return;
      }
      setCurrentSuggestion(suggestion);
      setEditorMeta(
        suggestion
          ? `Ready in ${payload.latency_ms ?? 0} ms. Press Tab to accept.`
          : "No suggestion returned yet.",
      );
    } catch (error) {
      if (requestId !== editorRequestIdRef.current) {
        return;
      }
      setCurrentSuggestion("");
      setEditorMeta(error instanceof Error ? error.message : "Generation failed");
    }
  }

  async function generateAssistantDraft() {
    if (!assistantInput.trim()) {
      setAssistantMeta("Enter a prompt or source text first.");
      return;
    }
    setAssistantMeta("Generating...");
    setAssistantOutput("");
    try {
      const payload = await generateRemote({
        text: assistantInput,
        mode: assistantMode,
        max_new_tokens: assistantMode === "assistant_continue" ? 120 : 180,
        temperature: 0.7,
        top_p: 0.95,
      });
      setAssistantOutput((payload.completion ?? "").trim());
      setAssistantMeta(`Generated in ${payload.latency_ms ?? 0} ms`);
    } catch (error) {
      setAssistantMeta(error instanceof Error ? error.message : "Generation failed");
    }
  }

  function updateEditorSelection() {
    const element = editorInputRef.current;
    if (!element) {
      return;
    }

    const start = element.selectionStart ?? 0;
    const end = element.selectionEnd ?? 0;
    if (start === end) {
      setEditorSelection(null);
      return;
    }

    const text = editorInput.slice(start, end).trim();
    if (!text) {
      setEditorSelection(null);
      return;
    }

    setEditorSelection({ start, end, text });
  }

  async function generateSelectionComment() {
    if (!editorSelection?.text) {
      setSelectionCommentMeta("Highlight the passage you want feedback on first.");
      return;
    }

    setSelectionCommentMeta("Generating comment...");
    try {
      const payload = await generateRemote({
        text: buildSelectionCommentRequest(
          editorInput,
          editorSelection.text,
          commentInstruction,
        ),
        mode: "assistant_comment",
        max_new_tokens: 120,
        temperature: 0.55,
        top_p: 0.95,
      });
      const comment = (payload.completion ?? "").trim();
      setSelectionComment(
        comment
          ? {
              selection: editorSelection.text,
              comment,
            }
          : null,
      );
      setSelectionCommentMeta(
        comment ? `Comment ready in ${payload.latency_ms ?? 0} ms` : "No comment returned yet.",
      );
    } catch (error) {
      setSelectionComment(null);
      setSelectionCommentMeta(error instanceof Error ? error.message : "Generation failed");
    }
  }

  function acceptSuggestion() {
    if (!currentSuggestion) {
      return;
    }
    setEditorInput((current) => current + currentSuggestion);
    setCurrentSuggestion("");
    setEditorMeta("Suggestion accepted.");
  }

  function dismissSuggestion(message = "Suggestion dismissed.") {
    setCurrentSuggestion("");
    setEditorMeta(message);
  }

  function sendAssistantToEditor() {
    if (!assistantOutput.trim()) {
      return;
    }
    setEditorInput((current) =>
      `${current}${current ? "\n\n" : ""}${assistantOutput.trim()}`,
    );
    setActiveTab("editor");
    setCurrentSuggestion("");
    setEditorMeta("Draft moved into the editor.");
  }

  function handleTabSelect(tabId: TabId) {
    if ((tabId === "editor" || tabId === "assistant") && !setupComplete) {
      setActiveTab("directions");
      return;
    }
    setActiveTab(tabId);
  }

  async function handleExpiredGoogleSession(message: string) {
    setSetupError(message);
    setSetupMessage(null);
    setDriveFiles([]);
    setSelectedFileIds([]);
    setUserState(null);
    await signOut({ callbackUrl: "/?reauth=drive" });
  }

  function syncEditorGhostScroll() {
    if (!editorInputRef.current || !editorGhostRef.current) {
      return;
    }
    editorGhostRef.current.scrollTop = editorInputRef.current.scrollTop;
    editorGhostRef.current.scrollLeft = editorInputRef.current.scrollLeft;
  }

  const documentsIngested =
    userState?.documents_ingested ?? ingestResult?.documents_ingested ?? 0;
  const chunksCreated =
    userState?.chunks_created ?? ingestResult?.chunks_created ?? 0;
  const hasCorpus = Boolean(userState?.has_corpus ?? ingestResult);
  const hasBundle =
    Boolean(bundleResult) || (userState?.available_bundles?.length ?? 0) > 0;
  const remoteHealthError = getRemoteHealthError(healthPayload);
  const remoteConnected = Boolean(verifiedRemoteUrl);
  const remoteUsable = remoteConnected && !remoteHealthError;
  const setupSteps: SetupStep[] = [
    {
      id: "auth",
      label: "Authenticate with Google",
      detail: session?.user?.email
        ? `Signed in as ${session.user.email}`
        : "Connect Google Drive access before building your corpus.",
      done: Boolean(session?.user?.email),
      tab: "setup",
    },
    {
      id: "corpus",
      label: "Ingest writing samples",
      detail: hasCorpus
        ? `${documentsIngested} docs and ${chunksCreated} chunks are ready.`
        : "Pull recent docs or hand-pick the exact Google Docs to use.",
      done: hasCorpus,
      tab: "setup",
    },
    {
      id: "bundle",
      label: "Build the Colab bundle",
      detail: hasBundle
        ? `Bundle ready${bundleResult ? `: ${bundleResult.bundle_name}.zip` : "."}`
        : "Generate the zip that contains the dataset, training scripts, and notebook.",
      done: hasBundle,
      tab: "setup",
    },
    {
      id: "remote",
      label: "Verify the inference endpoint",
      detail: remoteUsable
        ? `Verified remote: ${verifiedRemoteUrl}`
        : remoteError ||
          "Paste the ngrok URL from Colab and verify that the adapter exists.",
      done: remoteUsable,
      tab: "inference",
    },
  ];
  const remainingSteps = setupSteps.filter((step) => !step.done);
  const setupComplete = remainingSteps.length === 0;
  const nextRequiredTab = remainingSteps[0]?.tab ?? "editor";
  const filteredDriveFiles = driveFiles.filter((file) => {
    const query = driveSearch.trim().toLowerCase();
    if (!query) {
      return true;
    }
    return file.name.toLowerCase().includes(query);
  });
  const lockedGenerationSurface =
    !setupComplete && (activeTab === "editor" || activeTab === "assistant");
  const backendSummary = remoteUsable
    ? `Inference working at ${verifiedRemoteUrl}`
    : remoteError
      ? `Inference blocked: ${remoteError}`
      : "No verified remote inference URL connected";
  const tabItems: Array<{
    id: TabId;
    label: string;
    kicker: string;
    locked?: boolean;
  }> = [
    {
      id: "directions",
      label: "Directions",
      kicker: `${setupSteps.filter((step) => step.done).length}/4 done`,
    },
    { id: "setup", label: "Setup", kicker: "Corpus" },
    {
      id: "inference",
      label: "Inference",
      kicker: remoteUsable ? "Live" : "Pending",
    },
    {
      id: "editor",
      label: "Editor",
      kicker: setupComplete ? "Ready" : "Locked",
      locked: !setupComplete,
    },
    {
      id: "assistant",
      label: "Assistant",
      kicker: setupComplete ? "Ready" : "Locked",
      locked: !setupComplete,
    },
  ];

  useEffect(() => {
    syncEditorGhostScroll();
  }, [editorInput, currentSuggestion]);

  if (status === "loading") {
    return (
      <main style={styles.loadingShell}>
        <p style={styles.loadingText}>Loading...</p>
      </main>
    );
  }

  return (
    <main style={styles.page}>
      <div style={styles.shell}>
        <section style={styles.hero}>
          <div style={styles.heroGlow} />
          <div style={styles.heroCopy}>
            <Image
              src="/chatgpme-full-logo.png"
              alt="ChatGPMe"
              width={1108}
              height={388}
              priority
              style={styles.heroLogo}
            />
            <p style={styles.subtitle}>
              Ingest your Google Docs, package your training bundle for Colab,
              and wire the resulting inference endpoint back into a writing
              environment that only unlocks when the pipeline is actually live.
            </p>
          </div>
          <div style={styles.heroRail}>
            <div style={styles.heroStat}>
              <span style={styles.heroStatLabel}>Status</span>
              <strong style={styles.heroStatValue}>
                {setupComplete ? "Ready" : "In progress"}
              </strong>
            </div>
            <div style={styles.heroStat}>
              <span style={styles.heroStatLabel}>Corpus</span>
              <strong style={styles.heroStatValue}>{documentsIngested} docs</strong>
            </div>
            <div style={styles.heroStat}>
              <span style={styles.heroStatLabel}>Inference</span>
              <strong style={styles.heroStatValue}>
                {remoteUsable ? "Verified" : "Offline"}
              </strong>
            </div>
          </div>
        </section>

        {status === "authenticated" && (
          <header style={styles.topbar}>
            <div style={styles.statusPill}>{backendSummary}</div>
            <div style={styles.progressPill}>
              {setupSteps.filter((step) => step.done).length} of 4 steps done
            </div>
          </header>
        )}

        {!session ? (
          <section style={styles.guestSection}>
            <div style={styles.guestIntro}>
              <p style={styles.eyebrow}>How it works</p>
              <h2 style={styles.guestTitle}>Train your own writing model, then use it live.</h2>
              <p style={styles.sectionCopy}>
                ChatGPMe takes your Google Docs, packages a Colab training bundle,
                and reconnects the resulting inference endpoint back into the app
                for continuation suggestions, drafting, and line comments.
              </p>
              <div style={styles.guestSteps}>
                <div style={styles.guestStep}>
                  <span style={styles.guestStepNumber}>01</span>
                  <div>
                    <strong style={styles.guestStepTitle}>Connect Google Drive</strong>
                    <p style={styles.guestStepCopy}>Choose recent docs or hand-pick the exact files you want in the corpus.</p>
                  </div>
                </div>
                <div style={styles.guestStep}>
                  <span style={styles.guestStepNumber}>02</span>
                  <div>
                    <strong style={styles.guestStepTitle}>Train in Colab</strong>
                    <p style={styles.guestStepCopy}>Download the generated bundle, run the notebook, and start the remote inference server.</p>
                  </div>
                </div>
                <div style={styles.guestStep}>
                  <span style={styles.guestStepNumber}>03</span>
                  <div>
                    <strong style={styles.guestStepTitle}>Paste the inference link</strong>
                    <p style={styles.guestStepCopy}>Bring the ngrok URL back here and unlock the writing surfaces with your trained adapter.</p>
                  </div>
                </div>
              </div>
            </div>

            <aside style={styles.authCard}>
              <div style={styles.authBadge}>
                <Image
                  src="/chatgpme-icon.png"
                  alt="ChatGPMe mark"
                  width={56}
                  height={58}
                />
                <div>
                  <p style={styles.eyebrow}>Get started</p>
                  <h3 style={styles.authTitle}>Start with Google Drive</h3>
                </div>
              </div>
              <p style={styles.sectionCopy}>
                Sign in to ingest your docs, build the bundle, and wire the final
                Colab inference URL back into ChatGPMe.
              </p>
              {setupError && <div style={styles.errorBox}>{setupError}</div>}
              <button style={styles.primaryButton} onClick={() => signIn("google")}>
                Sign in with Google
              </button>
            </aside>
          </section>
        ) : (
          <>
            <section style={styles.userCard}>
              <div style={styles.userRow}>
                {session.user?.image && (
                  <img
                    src={session.user.image}
                    alt="avatar"
                    width={48}
                    height={48}
                    style={{ borderRadius: "50%" }}
                  />
                )}
                <div style={{ flex: 1 }}>
                  <div style={styles.userName}>{session.user?.name}</div>
                  <div style={styles.userEmail}>{session.user?.email}</div>
                </div>
                <button style={styles.ghostButton} onClick={() => signOut()}>
                  Sign out
                </button>
              </div>
            </section>

            <nav style={styles.tabs}>
              {tabItems.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => handleTabSelect(tab.id)}
                  style={
                    activeTab === tab.id
                      ? { ...styles.tab, ...styles.tabActive }
                      : tab.locked
                        ? { ...styles.tab, ...styles.tabLocked }
                        : styles.tab
                  }
                >
                  <span style={styles.tabKicker}>{tab.kicker}</span>
                  <span style={styles.tabLabel}>{tab.label}</span>
                </button>
              ))}
            </nav>

            {activeTab === "setup" && (
              <section style={styles.panelGrid}>
                <section style={styles.cardLarge}>
                  <div style={styles.cardHeader}>
                    <h2 style={styles.sectionTitle}>1. Ingest Your Corpus</h2>
                    <p style={styles.sectionCopy}>
                      Choose whether to import the latest Google Docs or hand-pick
                      the exact files that define the writing voice you want.
                    </p>
                  </div>

                  <div style={styles.toggleRow}>
                    <button
                      style={
                        sourceMode === "recent"
                          ? { ...styles.toggleButton, ...styles.toggleActive }
                          : styles.toggleButton
                      }
                      onClick={() => setSourceMode("recent")}
                    >
                      Last N Docs
                    </button>
                    <button
                      style={
                        sourceMode === "selection"
                          ? { ...styles.toggleButton, ...styles.toggleActive }
                          : styles.toggleButton
                      }
                      onClick={() => setSourceMode("selection")}
                    >
                      Select Specific Docs
                    </button>
                  </div>

                  <div style={styles.formRow}>
                    <label style={styles.label}>
                      Max files
                      <input
                        type="number"
                        min={1}
                        max={5000}
                        value={maxFiles}
                        onChange={(e) => setMaxFiles(Number(e.target.value))}
                        style={styles.input}
                      />
                    </label>
                    <label style={styles.checkboxLabel}>
                      <input
                        type="checkbox"
                        checked={ownerOnly}
                        onChange={(e) => setOwnerOnly(e.target.checked)}
                      />
                      Owner-only docs
                    </label>
                    <button
                      style={styles.secondaryButton}
                      onClick={() => void loadDriveFiles(true)}
                      disabled={listingFiles}
                    >
                      {listingFiles ? "Refreshing..." : "Refresh List"}
                    </button>
                  </div>

                  <div style={styles.filePanel}>
                    <div style={styles.filePanelHeader}>
                      <div>
                        <div style={styles.filePanelTitle}>
                          {sourceMode === "recent"
                            ? `Latest ${maxFiles} docs that will be ingested`
                            : "Select the exact docs to ingest"}
                        </div>
                        <p style={styles.filePanelCopy}>
                          {sourceMode === "recent"
                            ? "This preview updates automatically when you change the filters above."
                            : "Search, select all visible docs, or deselect them before ingesting."}
                        </p>
                      </div>

                      {sourceMode === "selection" && (
                        <div style={styles.fileToolbar}>
                          <input
                            value={driveSearch}
                            onChange={(e) => setDriveSearch(e.target.value)}
                            placeholder="Search docs..."
                            style={styles.searchInput}
                          />
                          <button
                            style={styles.secondaryButton}
                            onClick={() =>
                              selectAllVisibleFiles(filteredDriveFiles.map((file) => file.id))
                            }
                            disabled={filteredDriveFiles.length === 0}
                          >
                            Select All Visible
                          </button>
                          <button
                            style={styles.secondaryButton}
                            onClick={() =>
                              clearVisibleFiles(filteredDriveFiles.map((file) => file.id))
                            }
                            disabled={selectedFileIds.length === 0}
                          >
                            Deselect Visible
                          </button>
                        </div>
                      )}
                    </div>

                    <div style={styles.filePicker}>
                      {listingFiles && driveFiles.length === 0 ? (
                        <p style={styles.mutedText}>Loading your Google Drive docs...</p>
                      ) : filteredDriveFiles.length === 0 ? (
                        <p style={styles.mutedText}>
                          {driveFiles.length === 0
                            ? "No Google Docs matched the current filters."
                            : "No docs matched your search."}
                        </p>
                      ) : (
                        filteredDriveFiles.map((file) => {
                          const checked = selectedFileIds.includes(file.id);
                          return (
                            <label
                              key={file.id}
                              style={
                                sourceMode === "recent"
                                  ? { ...styles.fileRow, ...styles.fileRowPassive }
                                  : styles.fileRow
                              }
                            >
                              {sourceMode === "selection" ? (
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={() => toggleSelectedFile(file.id)}
                                />
                              ) : (
                                <div style={styles.fileRowBadge}>Included</div>
                              )}
                              <div style={{ flex: 1 }}>
                                <div style={styles.fileName}>{file.name}</div>
                                <div style={styles.fileMeta}>
                                  {file.modified_time
                                    ? `Modified ${new Date(file.modified_time).toLocaleString()}`
                                    : "No modified time"}
                                </div>
                              </div>
                            </label>
                          );
                        })
                      )}
                    </div>

                    {sourceMode === "selection" && (
                      <div style={styles.selectionMeta}>
                        {selectedFileIds.length} doc{selectedFileIds.length === 1 ? "" : "s"} selected
                      </div>
                    )}
                  </div>

                  <div style={styles.actionRow}>
                    <button
                      style={styles.primaryButton}
                      onClick={handleIngest}
                      disabled={ingesting}
                    >
                      {ingesting ? "Ingesting..." : "Ingest Google Drive Docs"}
                    </button>
                  </div>

                  {setupMessage && <div style={styles.successBox}>{setupMessage}</div>}
                  {setupError && <div style={styles.errorBox}>{setupError}</div>}
                </section>

                <section style={styles.cardSide}>
                  <div style={styles.cardHeader}>
                    <h2 style={styles.sectionTitle}>2. Build Colab Bundle</h2>
                    <p style={styles.sectionCopy}>
                      Generate a zip with `style_train.jsonl`, training scripts,
                      and the Colab notebook needed to produce your adapter.
                    </p>
                  </div>

                  <div style={styles.metricList}>
                    <div style={styles.metricTile}>
                      <span style={styles.metricLabel}>Documents</span>
                      <strong style={styles.metricValue}>{documentsIngested}</strong>
                    </div>
                    <div style={styles.metricTile}>
                      <span style={styles.metricLabel}>Training rows</span>
                      <strong style={styles.metricValue}>
                        {userState?.style_train_rows ?? chunksCreated}
                      </strong>
                    </div>
                  </div>

                  <button
                    style={styles.primaryButton}
                    onClick={handleBuildBundle}
                    disabled={buildingBundle || !userState?.has_corpus}
                  >
                    {buildingBundle ? "Building..." : "Generate Colab Bundle"}
                  </button>

                  {bundleResult && (
                    <div style={styles.bundleBox}>
                      <p>
                        Bundle ready: <strong>{bundleResult.bundle_name}.zip</strong>
                      </p>
                      <p style={styles.smallCopy}>
                        Dataset rows: {bundleResult.dataset_rows}. Adapter output
                        folder: `{bundleResult.adapter_dir_name}`
                      </p>
                      <a
                        href={`/api/bundle/download?bundleName=${encodeURIComponent(bundleResult.bundle_name)}`}
                        style={styles.downloadLink}
                      >
                        Download Bundle
                      </a>
                    </div>
                  )}

                  <div style={styles.stepsBox}>
                    <h3 style={styles.stepsTitle}>Colab handoff</h3>
                    <ol style={styles.stepsList}>
                      <li>Download the bundle zip.</li>
                      <li>Upload it to Colab and open the included notebook.</li>
                      <li>Run training, then launch the remote inference server.</li>
                      <li>Copy the ngrok URL into the Inference tab.</li>
                    </ol>
                  </div>
                </section>
              </section>
            )}

            {activeTab === "directions" && (
              <section style={styles.completeGrid}>
                <section style={styles.cardLarge}>
                  <div style={styles.cardHeader}>
                    <h2 style={styles.sectionTitle}>Directions</h2>
                    <p style={styles.sectionCopy}>
                      Run the workflow in this order: ingest your docs, generate
                      the Colab bundle, train in Colab, launch the remote
                      inference server, then paste the ngrok URL back into this
                      app. The writing tabs stay locked until that path is real.
                    </p>
                  </div>

                  <div style={styles.stepsBox}>
                    <h3 style={styles.stepsTitle}>End-to-end flow</h3>
                    <ol style={styles.stepsList}>
                      <li>Open the Setup tab and choose `Last N Docs` or `Select Specific Docs`.</li>
                      <li>Ingest the corpus and build the personalized Colab bundle zip.</li>
                      <li>Download the bundle and run the included notebook in Colab.</li>
                      <li>Start the remote inference server and expose it with ngrok.</li>
                      <li>Paste the ngrok URL into the Inference tab and verify it.</li>
                      <li>Use Editor and Assistant only after the remote endpoint is verified.</li>
                    </ol>
                  </div>

                  <div style={styles.checklist}>
                    {setupSteps.map((step, index) => (
                      <div
                        key={step.id}
                        style={
                          step.done
                            ? { ...styles.checklistItem, ...styles.checklistDone }
                            : styles.checklistItem
                        }
                      >
                        <div style={styles.checklistMarker}>
                          {step.done ? "0" + (index + 1) : index + 1}
                        </div>
                        <div style={{ flex: 1 }}>
                          <div style={styles.checklistLabel}>{step.label}</div>
                          <p style={styles.checklistDetail}>{step.detail}</p>
                        </div>
                        {!step.done && (
                          <button
                            style={styles.secondaryButton}
                            onClick={() => setActiveTab(step.tab)}
                          >
                            Open {step.tab === "setup" ? "Setup" : "Inference"}
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </section>

                <section style={styles.cardSide}>
                  <div style={styles.cardHeader}>
                    <h2 style={styles.sectionTitle}>Release Status</h2>
                    <p style={styles.sectionCopy}>
                      This is the final gate before generation surfaces unlock.
                    </p>
                  </div>

                  <div style={styles.releaseBox}>
                    <span style={styles.releaseLabel}>State</span>
                    <strong style={styles.releaseValue}>
                      {setupComplete ? "Unlocked" : "Blocked"}
                    </strong>
                    <p style={styles.releaseCopy}>
                      {setupComplete
                        ? "Editor and Assistant are live with a verified remote adapter."
                        : `${remainingSteps.length} required step${remainingSteps.length === 1 ? "" : "s"} still missing.`}
                    </p>
                  </div>

                  <div style={styles.actionColumn}>
                    <button
                      style={styles.primaryButton}
                      onClick={() =>
                        handleTabSelect(setupComplete ? "editor" : nextRequiredTab)
                      }
                    >
                      {setupComplete ? "Open Editor" : "Go To Required Step"}
                    </button>
                    <button
                      style={styles.secondaryButton}
                      onClick={() => setActiveTab("inference")}
                    >
                      Review Inference
                    </button>
                  </div>
                </section>
              </section>
            )}

            {activeTab === "inference" && (
              <section style={styles.inferencePanel}>
                <div style={styles.cardLarge}>
                  <div style={styles.cardHeader}>
                    <h2 style={styles.sectionTitle}>Remote Inference</h2>
                    <p style={styles.sectionCopy}>
                      Paste the ngrok URL from the Colab remote inference server.
                      The app will only accept it if the health check resolves to
                      a ChatGPMe backend with an adapter present.
                    </p>
                  </div>

                  <label style={styles.labelWide}>
                    Ngrok URL
                    <input
                      value={remoteUrlInput}
                      onChange={(e) => {
                        const nextValue = e.target.value;
                        setRemoteUrlInput(nextValue);
                        if (
                          verifiedRemoteUrl &&
                          normalizeRemoteUrl(nextValue) !== verifiedRemoteUrl
                        ) {
                          setVerifiedRemoteUrl("");
                          setHealthPayload(null);
                          setRemoteError(
                            "Inference URL changed. Re-verify before generating.",
                          );
                          window.localStorage.removeItem(REMOTE_URL_STORAGE_KEY);
                        }
                      }}
                      placeholder="https://your-ngrok-url.ngrok-free.app"
                      style={styles.inputWide}
                    />
                  </label>

                  <div style={styles.actionRow}>
                    <button
                      style={styles.primaryButton}
                      onClick={() => testRemote()}
                      disabled={testingRemote}
                    >
                      {testingRemote ? "Testing..." : "Verify And Save URL"}
                    </button>
                    {verifiedRemoteUrl && (
                      <button
                        style={styles.secondaryButton}
                        onClick={() => {
                          setVerifiedRemoteUrl("");
                          setHealthPayload(null);
                          setRemoteError("Inference URL cleared.");
                          window.localStorage.removeItem(REMOTE_URL_STORAGE_KEY);
                        }}
                      >
                        Clear URL
                      </button>
                    )}
                  </div>

                  {remoteError && <div style={styles.errorBox}>{remoteError}</div>}
                  {healthPayload && (
                    <div style={styles.healthBox}>
                      <div style={styles.metricTile}>
                        <span style={styles.metricLabel}>Status</span>
                        <strong style={styles.metricValue}>
                          {remoteUsable ? "Verified" : "Rejected"}
                        </strong>
                      </div>
                      <div style={styles.metricTile}>
                        <span style={styles.metricLabel}>Ready</span>
                        <strong style={styles.metricValue}>
                          {healthPayload.backend?.ready ? "Yes" : "No"}
                        </strong>
                      </div>
                      <div style={styles.metricTile}>
                        <span style={styles.metricLabel}>Adapter found</span>
                        <strong style={styles.metricValue}>
                          {healthPayload.backend?.adapter_exists ? "Yes" : "No"}
                        </strong>
                      </div>
                      <div style={styles.metricTile}>
                        <span style={styles.metricLabel}>Model</span>
                        <strong style={styles.metricValue}>
                          {healthPayload.backend?.model_name ?? "Unknown"}
                        </strong>
                      </div>
                      <div style={styles.urlBox}>
                        <span style={styles.metricLabel}>Verified URL</span>
                        <strong style={styles.urlValue}>
                          {verifiedRemoteUrl || "None"}
                        </strong>
                      </div>
                      {healthPayload.backend?.error && (
                        <p style={styles.remoteErrorText}>
                          {healthPayload.backend.error}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </section>
            )}

            {activeTab === "editor" && (
              <section style={styles.lockedSection}>
                <div
                  style={
                    lockedGenerationSurface
                      ? styles.lockedPanelContent
                      : styles.openPanelContent
                  }
                >
                  <section style={styles.panelGrid}>
                    <section style={{ ...styles.cardLarge, gridTemplateRows: "auto 1fr", minHeight: "100%" }}>
                      <div style={styles.cardHeader}>
                        <h2 style={styles.sectionTitle}>Editor</h2>
                        <p style={styles.sectionCopy}>
                          Type normally. Press ` to request a continuation,
                          Tab to accept it, and Esc to dismiss it.
                        </p>
                      </div>
                      <div style={styles.editorShell}>
                        <pre ref={editorGhostRef} style={styles.editorGhost} aria-hidden="true">
                          {editorInput}
                          <span style={styles.editorGhostSuggestion}>
                            {currentSuggestion}
                          </span>
                          {editorInput.endsWith("\n") ? "\n" : ""}
                        </pre>
                        <textarea
                          ref={editorInputRef}
                          value={editorInput}
                          onChange={(e) => {
                            setEditorInput(e.target.value);
                            if (currentSuggestion) {
                              setCurrentSuggestion("");
                            }
                            const trimmed = e.target.value.trim();
                            setEditorMeta(
                              trimmed.length === 0
                                ? "Idle"
                                : trimmed.length < 20
                                  ? "Add a bit more text to get a continuation."
                                  : "Press ` (top left below Escape) to request a continuation.",
                            );
                          }}
                          onSelect={updateEditorSelection}
                          onKeyUp={updateEditorSelection}
                          onMouseUp={updateEditorSelection}
                          onScroll={syncEditorGhostScroll}
                          onKeyDown={(e) => {
                            if (e.key === "`" && !e.shiftKey && !e.metaKey && !e.ctrlKey && !e.altKey) {
                              e.preventDefault();
                              void requestEditorSuggestion();
                            }
                            if (e.key === "Tab" && currentSuggestion) {
                              e.preventDefault();
                              acceptSuggestion();
                            }
                            if (e.key === "Escape" && currentSuggestion) {
                              e.preventDefault();
                              dismissSuggestion();
                            }
                          }}
                          placeholder="Start writing here..."
                          style={styles.editorArea}
                        />
                      </div>
                    </section>

                    <section style={styles.cardSide}>
                      <div style={styles.sideSection}>
                        <div style={styles.cardHeader}>
                          <h2 style={styles.sectionTitle}>Continuation</h2>
                          <p style={styles.sectionCopy}>{editorMeta}</p>
                        </div>
                        <p style={styles.mutedText}>
                          Press ` (top left below Escape) to generate. Press Tab to accept.
                        </p>
                        {!remoteUsable && (
                          <p style={styles.mutedText}>
                            Verify the remote inference URL in the Inference tab
                            before using suggestions.
                          </p>
                        )}
                      </div>

                      <div style={styles.sideSection}>
                        <div style={styles.cardHeader}>
                          <h2 style={styles.sectionTitle}>Comment On Selection</h2>
                          <p style={styles.sectionCopy}>{selectionCommentMeta}</p>
                        </div>
                        <div style={styles.selectionCard}>
                          <span style={styles.metricLabel}>Selected text</span>
                          <p style={styles.selectionPreview}>
                            {editorSelection?.text || "Highlight a passage in the editor to target it."}
                          </p>
                        </div>
                        <label style={styles.labelWide}>
                          Comment focus
                          <textarea
                            value={commentInstruction}
                            onChange={(e) => setCommentInstruction(e.target.value)}
                            placeholder="Optional: ask for clarity, tone, evidence, structure..."
                            style={styles.commentInput}
                          />
                        </label>
                        <button
                          style={styles.primaryButton}
                          onClick={generateSelectionComment}
                          disabled={!remoteUsable || !setupComplete || !editorSelection?.text}
                        >
                          Generate Comment
                        </button>
                        <div style={styles.commentBox}>
                          <span style={styles.metricLabel}>Latest comment</span>
                          {selectionComment ? (
                            <>
                              <blockquote style={styles.commentQuote}>
                                {selectionComment.selection}
                              </blockquote>
                              <p style={styles.commentBody}>{selectionComment.comment}</p>
                            </>
                          ) : (
                            <p style={styles.mutedText}>
                              The model will leave a short margin-style note here.
                            </p>
                          )}
                        </div>
                      </div>
                    </section>
                  </section>
                </div>

                {lockedGenerationSurface && (
                  <div style={styles.overlay}>
                    <div style={styles.overlayCard}>
                      <p style={styles.overlayEyebrow}>Generation locked</p>
                      <h3 style={styles.overlayTitle}>Finish the setup pipeline</h3>
                      <p style={styles.overlayCopy}>
                        The editor stays blocked until the corpus is ingested,
                        the Colab bundle is built, and the remote adapter URL is
                        verified.
                      </p>
                      <div style={styles.overlaySteps}>
                        {remainingSteps.map((step) => (
                          <div key={step.id} style={styles.overlayStep}>
                            <span style={styles.overlayStepDot} />
                            <span>{step.label}</span>
                          </div>
                        ))}
                      </div>
                      <div style={styles.actionRow}>
                        <button
                          style={styles.primaryButton}
                          onClick={() => handleTabSelect("directions")}
                        >
                          Open Directions
                        </button>
                        <button
                          style={styles.secondaryButton}
                          onClick={() => setActiveTab("inference")}
                        >
                          Fix Inference
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </section>
            )}

            {activeTab === "assistant" && (
              <section style={styles.lockedSection}>
                <div
                  style={
                    lockedGenerationSurface
                      ? styles.lockedPanelContent
                      : styles.openPanelContent
                  }
                >
                  <section style={styles.panelGrid}>
                    <section style={styles.cardLarge}>
                      <div style={styles.cardHeader}>
                        <h2 style={styles.sectionTitle}>Assistant</h2>
                        <p style={styles.sectionCopy}>
                          Generate drafts, rewrites, or continuations with the
                          exact adapter you verified in the Inference tab.
                        </p>
                      </div>
                      <label style={styles.labelWide}>
                        Mode
                        <select
                          value={assistantMode}
                          onChange={(e) => setAssistantMode(e.target.value)}
                          style={styles.select}
                        >
                          <option value="assistant_draft">Draft</option>
                          <option value="assistant_rewrite">Rewrite</option>
                          <option value="assistant_continue">Continue</option>
                        </select>
                      </label>
                      <label style={styles.labelWide}>
                        Prompt
                        <textarea
                          value={assistantInput}
                          onChange={(e) => setAssistantInput(e.target.value)}
                          placeholder="Describe the draft or paste text to rewrite..."
                          style={styles.assistantArea}
                        />
                      </label>
                      <div style={styles.actionRow}>
                        <button
                          style={styles.primaryButton}
                          onClick={generateAssistantDraft}
                          disabled={!remoteUsable || !setupComplete}
                        >
                          Generate
                        </button>
                        <button
                          style={styles.secondaryButton}
                          onClick={sendAssistantToEditor}
                          disabled={!assistantOutput.trim()}
                        >
                          Send To Editor
                        </button>
                      </div>
                    </section>

                    <section style={styles.cardSide}>
                      <div style={styles.cardHeader}>
                        <h2 style={styles.sectionTitle}>Result</h2>
                        <p style={styles.sectionCopy}>{assistantMeta}</p>
                      </div>
                      <pre style={styles.outputBox}>{assistantOutput}</pre>
                    </section>
                  </section>
                </div>

                {lockedGenerationSurface && (
                  <div style={styles.overlay}>
                    <div style={styles.overlayCard}>
                      <p style={styles.overlayEyebrow}>Assistant offline</p>
                      <h3 style={styles.overlayTitle}>No verified model path yet</h3>
                      <p style={styles.overlayCopy}>
                        This surface does not fall back to a generic model. If
                        the remote link is wrong or incomplete, generation stays
                        disabled.
                      </p>
                      <div style={styles.overlaySteps}>
                        {remainingSteps.map((step) => (
                          <div key={step.id} style={styles.overlayStep}>
                            <span style={styles.overlayStepDot} />
                            <span>{step.label}</span>
                          </div>
                        ))}
                      </div>
                      <div style={styles.actionRow}>
                        <button
                          style={styles.primaryButton}
                          onClick={() => handleTabSelect("directions")}
                        >
                          Open Directions
                        </button>
                        <button
                          style={styles.secondaryButton}
                          onClick={() => setActiveTab("setup")}
                        >
                          Back To Setup
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </section>
            )}
          </>
        )}
      </div>
    </main>
  );
}

function normalizeRemoteUrl(value: string) {
  return value.trim().replace(/\/+$/, "");
}

function getRemoteHealthError(payload: BackendHealth | null) {
  if (!payload) {
    return "No remote health payload found.";
  }
  if (payload.status !== "ok") {
    return "Remote health check did not return status ok.";
  }
  if (!payload.backend) {
    return "Remote URL is not a ChatGPMe inference server.";
  }
  if (!payload.backend.adapter_exists) {
    return "Remote server responded, but no trained adapter was found at that link.";
  }
  if (payload.backend.error) {
    return payload.backend.error;
  }
  return null;
}

function shortenSuggestion(text: string) {
  const cleaned = text.replace(/^\s+/, "");
  if (!cleaned) return "";
  const firstLine = cleaned.split("\n")[0];
  const sentenceBreak = firstLine.match(/^(.{0,160}?[.!?])(\s|$)/);
  if (sentenceBreak) return sentenceBreak[1];
  const words = firstLine.split(/\s+/).filter(Boolean);
  return words.slice(0, 18).join(" ");
}

function buildSelectionCommentRequest(
  fullDocument: string,
  selection: string,
  instruction: string,
) {
  const trimmedInstruction = instruction.trim();
  return [
    "Document context:",
    fullDocument.trim(),
    "",
    "Selected passage:",
    selection.trim(),
    "",
    "Comment focus:",
    trimmedInstruction || "Leave a concise, constructive margin comment on the selected passage.",
  ].join("\n");
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    background:
      "radial-gradient(circle at top left, rgba(13,92,99,0.08), transparent 30%), radial-gradient(circle at bottom right, rgba(180,95,6,0.10), transparent 24%), #f5f1e8",
    color: "#202124",
    padding: "24px 18px 60px",
  },
  shell: {
    maxWidth: 1280,
    margin: "0 auto",
  },
  hero: {
    position: "relative",
    overflow: "hidden",
    display: "grid",
    gridTemplateColumns: "minmax(0, 1.5fr) minmax(280px, 0.9fr)",
    gap: 18,
    padding: 28,
    borderRadius: 30,
    background:
      "linear-gradient(135deg, rgba(255,255,255,0.88), rgba(255,253,248,0.96))",
    border: "1px solid #d6cfc2",
    boxShadow: "0 18px 50px rgba(42,38,31,0.10)",
    marginBottom: 18,
  },
  heroGlow: {
    position: "absolute",
    inset: "auto -120px -140px auto",
    width: 340,
    height: 340,
    borderRadius: "50%",
    background: "radial-gradient(circle, rgba(13,92,99,0.14), transparent 68%)",
    pointerEvents: "none",
  },
  heroCopy: {
    position: "relative",
    zIndex: 1,
  },
  heroLogo: {
    width: "min(100%, 720px)",
    height: "auto",
    display: "block",
    marginBottom: 10,
  },
  eyebrow: {
    fontSize: 12,
    letterSpacing: "0.28em",
    textTransform: "uppercase",
    color: "#0d5c63",
    marginBottom: 12,
  },
  subtitle: {
    maxWidth: 760,
    color: "#63686d",
    lineHeight: 1.7,
    fontSize: 16,
  },
  heroRail: {
    position: "relative",
    zIndex: 1,
    display: "grid",
    gap: 12,
    alignContent: "end",
  },
  heroStat: {
    borderRadius: 18,
    padding: "16px 18px",
    background: "#fffdf8",
    border: "1px solid #d6cfc2",
  },
  heroStatLabel: {
    display: "block",
    fontSize: 12,
    textTransform: "uppercase",
    letterSpacing: "0.18em",
    color: "#6a6f73",
    marginBottom: 8,
  },
  heroStatValue: {
    fontSize: 22,
    color: "#202124",
  },
  topbar: {
    display: "flex",
    justifyContent: "space-between",
    gap: 14,
    alignItems: "center",
    flexWrap: "wrap",
    marginBottom: 18,
  },
  statusPill: {
    padding: "12px 16px",
    borderRadius: 999,
    background: "#fffdf8",
    border: "1px solid #d6cfc2",
    color: "#63686d",
    minWidth: 280,
  },
  progressPill: {
    padding: "12px 16px",
    borderRadius: 999,
    background: "#e4f0ef",
    border: "1px solid #b8d1cf",
    color: "#0d5c63",
    fontWeight: 700,
  },
  authCard: {
    background: "#fffdf8",
    border: "1px solid #d6cfc2",
    borderRadius: 24,
    boxShadow: "0 14px 38px rgba(42,38,31,0.10)",
    padding: 28,
    display: "grid",
    gap: 16,
    alignContent: "start",
  },
  guestSection: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1.4fr) minmax(320px, 0.9fr)",
    gap: 18,
    alignItems: "stretch",
  },
  guestIntro: {
    background: "#fffdf8",
    border: "1px solid #d6cfc2",
    borderRadius: 24,
    boxShadow: "0 14px 38px rgba(42,38,31,0.08)",
    padding: 28,
    display: "grid",
    gap: 18,
  },
  guestTitle: {
    fontSize: "clamp(1.9rem, 4vw, 3rem)",
    lineHeight: 1.02,
    letterSpacing: "-0.04em",
    fontWeight: 800,
    color: "#202124",
    maxWidth: 620,
  },
  authTitle: {
    fontSize: 22,
    fontWeight: 750,
    color: "#202124",
  },
  authBadge: {
    display: "grid",
    gridTemplateColumns: "56px 1fr",
    gap: 14,
    alignItems: "center",
  },
  guestSteps: {
    display: "grid",
    gap: 14,
  },
  guestStep: {
    display: "grid",
    gridTemplateColumns: "56px 1fr",
    gap: 14,
    alignItems: "start",
    padding: 16,
    borderRadius: 18,
    background: "#f7f3ea",
    border: "1px solid #e4dccb",
  },
  guestStepNumber: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: 56,
    height: 56,
    borderRadius: 999,
    background: "#0d5c63",
    color: "#fff",
    fontWeight: 800,
    letterSpacing: "0.08em",
    fontSize: 14,
  },
  guestStepTitle: {
    display: "block",
    fontSize: 17,
    fontWeight: 700,
    color: "#202124",
    marginBottom: 4,
  },
  guestStepCopy: {
    color: "#6a6f73",
    lineHeight: 1.6,
  },
  userCard: {
    background: "#fffdf8",
    border: "1px solid #d6cfc2",
    borderRadius: 24,
    boxShadow: "0 14px 38px rgba(42,38,31,0.08)",
    padding: 18,
    marginBottom: 18,
  },
  userRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
  },
  userName: {
    fontWeight: 700,
    color: "#202124",
  },
  userEmail: {
    fontSize: 13,
    color: "#6a6f73",
  },
  tabs: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
    gap: 10,
    marginBottom: 18,
  },
  tab: {
    display: "grid",
    gap: 6,
    padding: "14px 16px",
    borderRadius: 18,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: "#d6cfc2",
    background: "#fffdf8",
    color: "#202124",
    cursor: "pointer",
    textAlign: "left",
    boxShadow: "0 4px 12px rgba(42,38,31,0.04)",
  },
  tabActive: {
    background: "#0d5c63",
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: "#0d5c63",
    color: "#ffffff",
  },
  tabLocked: {
    opacity: 0.78,
  },
  tabKicker: {
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: "0.18em",
    opacity: 0.72,
  },
  tabLabel: {
    fontSize: 16,
    fontWeight: 700,
  },
  panelGrid: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1.7fr) minmax(320px, 1fr)",
    gap: 18,
  },
  completeGrid: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1.4fr) minmax(320px, 0.8fr)",
    gap: 18,
  },
  inferencePanel: {
    display: "grid",
  },
  lockedSection: {
    position: "relative",
  },
  openPanelContent: {
    position: "relative",
    zIndex: 1,
  },
  lockedPanelContent: {
    position: "relative",
    zIndex: 1,
    filter: "blur(1.5px)",
    opacity: 0.44,
    pointerEvents: "none",
  },
  cardLarge: {
    background: "#fffdf8",
    border: "1px solid #d6cfc2",
    borderRadius: 24,
    boxShadow: "0 14px 38px rgba(42,38,31,0.08)",
    padding: 22,
    display: "grid",
    gap: 18,
  },
  cardSide: {
    background: "#fffdf8",
    border: "1px solid #d6cfc2",
    borderRadius: 24,
    boxShadow: "0 14px 38px rgba(42,38,31,0.08)",
    padding: 22,
    display: "grid",
    gap: 18,
    alignContent: "start",
  },
  sideSection: {
    display: "grid",
    gap: 14,
  },
  cardHeader: {
    display: "grid",
    gap: 8,
  },
  sectionTitle: {
    fontSize: 24,
    fontWeight: 750,
    color: "#202124",
  },
  sectionCopy: {
    color: "#6a6f73",
    lineHeight: 1.7,
  },
  toggleRow: {
    display: "flex",
    gap: 10,
    flexWrap: "wrap",
  },
  toggleButton: {
    padding: "10px 14px",
    borderRadius: 14,
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: "#d6cfc2",
    background: "#fff",
    color: "#202124",
    cursor: "pointer",
  },
  toggleActive: {
    background: "#e4f0ef",
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: "#0d5c63",
    color: "#0d5c63",
  },
  formRow: {
    display: "flex",
    gap: 16,
    alignItems: "end",
    flexWrap: "wrap",
  },
  filePanel: {
    display: "grid",
    gap: 14,
    padding: 16,
    borderRadius: 18,
    background: "#f6f4ed",
    border: "1px solid #e4ddd1",
  },
  filePanelHeader: {
    display: "grid",
    gap: 12,
  },
  filePanelTitle: {
    fontSize: 17,
    fontWeight: 700,
    color: "#202124",
  },
  filePanelCopy: {
    marginTop: 4,
    color: "#6a6f73",
    lineHeight: 1.5,
  },
  fileToolbar: {
    display: "flex",
    gap: 10,
    flexWrap: "wrap",
    alignItems: "center",
  },
  label: {
    display: "grid",
    gap: 6,
    fontSize: 14,
    fontWeight: 700,
    color: "#202124",
  },
  labelWide: {
    display: "grid",
    gap: 6,
    fontSize: 14,
    fontWeight: 700,
    color: "#202124",
  },
  checkboxLabel: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontSize: 14,
    color: "#4f565b",
  },
  input: {
    width: 110,
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid #d6cfc2",
    background: "#fff",
    color: "#202124",
  },
  inputWide: {
    width: "100%",
    padding: "12px 14px",
    borderRadius: 14,
    border: "1px solid #d6cfc2",
    background: "#fff",
    color: "#202124",
    fontSize: 15,
  },
  select: {
    width: "100%",
    padding: "12px 14px",
    borderRadius: 14,
    border: "1px solid #d6cfc2",
    background: "#fff",
    color: "#202124",
  },
  filePicker: {
    maxHeight: 380,
    overflow: "auto",
    border: "1px solid #d6cfc2",
    borderRadius: 16,
    background: "#fff",
    padding: 4,
  },
  searchInput: {
    minWidth: 220,
    padding: "12px 14px",
    borderRadius: 12,
    border: "1px solid #d6cfc2",
    background: "#fff",
    color: "#202124",
    fontSize: 15,
  },
  fileRow: {
    display: "flex",
    gap: 12,
    alignItems: "flex-start",
    padding: "12px 14px",
    borderBottom: "1px solid #efeadf",
  },
  fileRowPassive: {
    alignItems: "center",
  },
  fileRowBadge: {
    flexShrink: 0,
    padding: "6px 10px",
    borderRadius: 999,
    background: "#e4f0ef",
    color: "#0d5c63",
    fontSize: 12,
    fontWeight: 700,
  },
  fileName: {
    fontWeight: 700,
    color: "#202124",
  },
  fileMeta: {
    marginTop: 4,
    color: "#6a6f73",
    fontSize: 13,
  },
  selectionMeta: {
    color: "#4f565b",
    fontSize: 14,
    fontWeight: 600,
  },
  actionRow: {
    display: "flex",
    gap: 10,
    flexWrap: "wrap",
  },
  actionColumn: {
    display: "grid",
    gap: 10,
  },
  primaryButton: {
    padding: "12px 16px",
    borderRadius: 14,
    border: "1px solid #0d5c63",
    background: "#0d5c63",
    color: "#ffffff",
    cursor: "pointer",
    fontWeight: 700,
  },
  secondaryButton: {
    padding: "12px 16px",
    borderRadius: 14,
    border: "1px solid #d6cfc2",
    background: "#fff",
    color: "#202124",
    cursor: "pointer",
    fontWeight: 700,
  },
  ghostButton: {
    padding: "8px 12px",
    borderRadius: 12,
    border: "1px solid #d6cfc2",
    background: "#fff",
    color: "#4f565b",
    cursor: "pointer",
  },
  successBox: {
    padding: 14,
    borderRadius: 14,
    background: "#e8f5e9",
    border: "1px solid #bfe5c6",
    color: "#1b5e20",
  },
  errorBox: {
    padding: 14,
    borderRadius: 14,
    background: "#ffebee",
    border: "1px solid #f3c7cf",
    color: "#b71c1c",
  },
  metricList: {
    display: "grid",
    gap: 12,
  },
  metricTile: {
    display: "grid",
    gap: 4,
    padding: 14,
    borderRadius: 16,
    background: "#fff",
    border: "1px solid #d6cfc2",
  },
  metricLabel: {
    fontSize: 12,
    letterSpacing: "0.16em",
    textTransform: "uppercase",
    color: "#6a6f73",
  },
  metricValue: {
    fontSize: 20,
    color: "#202124",
  },
  bundleBox: {
    borderRadius: 16,
    border: "1px solid #d6cfc2",
    background: "#fff",
    padding: 14,
    display: "grid",
    gap: 8,
  },
  smallCopy: {
    color: "#6a6f73",
    fontSize: 13,
    lineHeight: 1.6,
  },
  downloadLink: {
    color: "#0d5c63",
    fontWeight: 700,
    textDecoration: "none",
  },
  stepsBox: {
    borderRadius: 16,
    background: "#f6f4ed",
    border: "1px solid #e7e0d3",
    padding: 14,
  },
  stepsTitle: {
    fontSize: 16,
    fontWeight: 750,
    marginBottom: 8,
    color: "#202124",
  },
  stepsList: {
    paddingLeft: 18,
    color: "#4f565b",
    lineHeight: 1.8,
  },
  checklist: {
    display: "grid",
    gap: 12,
  },
  checklistItem: {
    display: "flex",
    gap: 14,
    alignItems: "center",
    padding: 16,
    borderRadius: 18,
    border: "1px solid #d6cfc2",
    background: "#fff",
  },
  checklistDone: {
    background: "#e4f0ef",
    border: "1px solid #b8d1cf",
  },
  checklistMarker: {
    width: 40,
    height: 40,
    borderRadius: 999,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#0d5c63",
    color: "#ffffff",
    fontWeight: 800,
    flexShrink: 0,
  },
  checklistLabel: {
    fontSize: 17,
    fontWeight: 750,
    color: "#202124",
  },
  checklistDetail: {
    marginTop: 4,
    color: "#6a6f73",
    lineHeight: 1.6,
  },
  releaseBox: {
    padding: 18,
    borderRadius: 18,
    background: "#f6f4ed",
    border: "1px solid #d6cfc2",
    display: "grid",
    gap: 8,
  },
  releaseLabel: {
    fontSize: 12,
    textTransform: "uppercase",
    letterSpacing: "0.16em",
    color: "#6a6f73",
  },
  releaseValue: {
    fontSize: 34,
    lineHeight: 1,
    color: "#202124",
  },
  releaseCopy: {
    color: "#4f565b",
    lineHeight: 1.7,
  },
  healthBox: {
    borderRadius: 18,
    border: "1px solid #d6cfc2",
    background: "#fff",
    padding: 14,
    display: "grid",
    gap: 10,
  },
  urlBox: {
    display: "grid",
    gap: 6,
    paddingTop: 6,
  },
  urlValue: {
    wordBreak: "break-word",
    color: "#202124",
  },
  remoteErrorText: {
    color: "#b71c1c",
    lineHeight: 1.6,
  },
  editorShell: {
    position: "relative",
    minHeight: 420,
    height: "100%",
  },
  editorGhost: {
    position: "absolute",
    inset: 0,
    margin: 0,
    padding: 16,
    border: "1px solid transparent",
    borderRadius: 16,
    color: "transparent",
    background: "#fff",
    whiteSpace: "pre-wrap",
    overflowWrap: "break-word",
    overflow: "hidden",
    pointerEvents: "none",
    lineHeight: 1.7,
    fontSize: 16,
    fontFamily: "inherit",
    zIndex: 1,
  },
  editorGhostSuggestion: {
    color: "rgba(32,33,36,0.34)",
  },
  editorArea: {
    minHeight: 420,
    height: "100%",
    width: "100%",
    position: "relative",
    borderRadius: 16,
    border: "1px solid #d6cfc2",
    background: "transparent",
    color: "#202124",
    padding: 16,
    resize: "vertical",
    lineHeight: 1.7,
    fontSize: 16,
    fontFamily: "inherit",
    zIndex: 2,
  },
  assistantArea: {
    minHeight: 260,
    width: "100%",
    borderRadius: 16,
    border: "1px solid #d6cfc2",
    background: "#fff",
    color: "#202124",
    padding: 16,
    resize: "vertical",
    lineHeight: 1.7,
    fontSize: 16,
  },
  outputBox: {
    minHeight: 300,
    whiteSpace: "pre-wrap",
    overflow: "auto",
    padding: 14,
    borderRadius: 16,
    border: "1px dashed #d6cfc2",
    background: "linear-gradient(180deg, #e4f0ef, rgba(255,255,255,0.7))",
    color: "#202124",
  },
  selectionCard: {
    display: "grid",
    gap: 8,
    padding: 14,
    borderRadius: 16,
    border: "1px solid #d6cfc2",
    background: "#f6f4ed",
  },
  selectionPreview: {
    color: "#202124",
    whiteSpace: "pre-wrap",
    lineHeight: 1.6,
  },
  commentInput: {
    minHeight: 88,
    width: "100%",
    borderRadius: 16,
    border: "1px solid #d6cfc2",
    background: "#fff",
    color: "#202124",
    padding: 14,
    resize: "vertical",
    lineHeight: 1.6,
    fontSize: 15,
    fontFamily: "inherit",
  },
  commentBox: {
    display: "grid",
    gap: 10,
    padding: 14,
    borderRadius: 16,
    border: "1px solid #d6cfc2",
    background: "#fff",
  },
  commentQuote: {
    margin: 0,
    padding: "12px 14px",
    borderLeft: "4px solid #b8d1cf",
    background: "#f6f4ed",
    color: "#4f565b",
    whiteSpace: "pre-wrap",
    lineHeight: 1.6,
  },
  commentBody: {
    color: "#202124",
    lineHeight: 1.7,
    whiteSpace: "pre-wrap",
  },
  mutedText: {
    color: "#6a6f73",
    lineHeight: 1.7,
  },
  overlay: {
    position: "absolute",
    inset: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 22,
    background: "rgba(32,33,36,0.18)",
    backdropFilter: "blur(8px)",
    borderRadius: 24,
    zIndex: 2,
  },
  overlayCard: {
    maxWidth: 560,
    width: "100%",
    padding: 24,
    borderRadius: 24,
    background: "#fffdf8",
    border: "1px solid #d6cfc2",
    boxShadow: "0 24px 60px rgba(42,38,31,0.18)",
    display: "grid",
    gap: 14,
  },
  overlayEyebrow: {
    fontSize: 12,
    textTransform: "uppercase",
    letterSpacing: "0.22em",
    color: "#0d5c63",
  },
  overlayTitle: {
    fontSize: 28,
    lineHeight: 1.05,
    color: "#202124",
  },
  overlayCopy: {
    color: "#63686d",
    lineHeight: 1.7,
  },
  overlaySteps: {
    display: "grid",
    gap: 10,
    padding: "4px 0",
  },
  overlayStep: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    color: "#202124",
  },
  overlayStepDot: {
    width: 10,
    height: 10,
    borderRadius: 999,
    background: "#0d5c63",
    boxShadow: "0 0 0 4px rgba(13,92,99,0.12)",
    flexShrink: 0,
  },
  loadingShell: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#f5f1e8",
  },
  loadingText: {
    color: "#202124",
  },
};
