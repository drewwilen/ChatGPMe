const tabs = document.querySelectorAll(".tab");
const panels = document.querySelectorAll(".tab-panel");
const backendStatus = document.getElementById("backendStatus");

const editorInput = document.getElementById("editorInput");
const editorGhost = document.getElementById("editorGhost");
const editorMeta = document.getElementById("editorMeta");
const acceptSuggestion = document.getElementById("acceptSuggestion");
const dismissSuggestion = document.getElementById("dismissSuggestion");

const assistantMode = document.getElementById("assistantMode");
const assistantInput = document.getElementById("assistantInput");
const assistantOutput = document.getElementById("assistantOutput");
const assistantMeta = document.getElementById("assistantMeta");
const generateAssistant = document.getElementById("generateAssistant");
const sendToEditor = document.getElementById("sendToEditor");

let currentSuggestion = "";
let editorTimer = null;

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    tabs.forEach((item) => item.classList.toggle("is-active", item === tab));
    panels.forEach((panel) => panel.classList.toggle("is-active", panel.dataset.panel === tab.dataset.tab));
  });
});

async function fetchHealth() {
  const response = await fetch("/api/health");
  const payload = await response.json();
  const backend = payload.backend || {};
  if (backend.ready) {
    backendStatus.textContent = `Ready: ${backend.model_name}`;
  } else if (backend.adapter_exists) {
    backendStatus.textContent = `Adapter found, lazy load pending`;
  } else {
    backendStatus.textContent = backend.error || "Model not ready";
  }
}

async function generateText({ text, mode, max_new_tokens, temperature, top_p }) {
  const response = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, mode, max_new_tokens, temperature, top_p }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Generation failed.");
  }
  return payload;
}

function clearSuggestion() {
  currentSuggestion = "";
  renderGhostText();
  editorMeta.textContent = "Idle";
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function shortenSuggestion(text) {
  const cleaned = text.replace(/^\s+/, "");
  if (!cleaned) return "";
  const firstLine = cleaned.split("\n")[0];
  const sentenceBreak = firstLine.match(/^(.{0,140}?[.!?])(\s|$)/);
  if (sentenceBreak) return sentenceBreak[1];
  const words = firstLine.split(/\s+/).filter(Boolean);
  return words.slice(0, 12).join(" ");
}

function renderGhostText() {
  const base = editorInput.value || "";
  const suffix = currentSuggestion ? `<span class="editor-ghost-suggestion">${escapeHtml(currentSuggestion)}</span>` : "";
  editorGhost.innerHTML = `${escapeHtml(base)}${suffix}${base.endsWith("\n") ? "\n" : ""}`;
  editorGhost.scrollTop = editorInput.scrollTop;
  editorGhost.scrollLeft = editorInput.scrollLeft;
}

async function requestEditorSuggestion() {
  const text = editorInput.value;
  if (text.trim().length < 20) {
    clearSuggestion();
    return;
  }
  editorMeta.textContent = "Generating suggestion…";
  try {
    const payload = await generateText({
      text,
      mode: "editor_continue",
      max_new_tokens: 20,
      temperature: 0.45,
      top_p: 0.95,
    });
    currentSuggestion = shortenSuggestion(payload.completion || "");
    renderGhostText();
    editorMeta.textContent = `Ready in ${payload.latency_ms} ms`;
  } catch (error) {
    currentSuggestion = "";
    renderGhostText();
    editorMeta.textContent = error.message;
  }
}

editorInput.addEventListener("input", () => {
  clearTimeout(editorTimer);
  renderGhostText();
  editorTimer = setTimeout(requestEditorSuggestion, 650);
});

editorInput.addEventListener("scroll", renderGhostText);

editorInput.addEventListener("keydown", (event) => {
  if (event.key === "Tab" && currentSuggestion) {
    event.preventDefault();
    editorInput.value += currentSuggestion;
    clearSuggestion();
  }
  if (event.key === "Escape") {
    clearSuggestion();
  }
});

acceptSuggestion.addEventListener("click", () => {
  if (!currentSuggestion) return;
  editorInput.value += currentSuggestion;
  clearSuggestion();
});

dismissSuggestion.addEventListener("click", clearSuggestion);

generateAssistant.addEventListener("click", async () => {
  const text = assistantInput.value.trim();
  if (!text) {
    assistantMeta.textContent = "Enter a writing request or source text first.";
    return;
  }
  assistantMeta.textContent = "Generating…";
  assistantOutput.textContent = "";
  try {
    const payload = await generateText({
      text,
      mode: assistantMode.value,
      max_new_tokens: assistantMode.value === "assistant_continue" ? 120 : 180,
      temperature: 0.7,
      top_p: 0.95,
    });
    assistantOutput.textContent = (payload.completion || "").trim();
    assistantMeta.textContent = `Generated in ${payload.latency_ms} ms`;
  } catch (error) {
    assistantMeta.textContent = error.message;
  }
});

sendToEditor.addEventListener("click", () => {
  const text = assistantOutput.textContent.trim();
  if (!text) return;
  editorInput.value = `${editorInput.value}${editorInput.value ? "\n\n" : ""}${text}`;
  document.querySelector('[data-tab="editor"]').click();
  clearSuggestion();
});

fetchHealth().catch(() => {
  backendStatus.textContent = "Backend unavailable";
});

renderGhostText();
