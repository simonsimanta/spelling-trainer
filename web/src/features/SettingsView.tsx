import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  RefreshCcw,
  XCircle
} from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { getJson, patchJson, postJson } from "../api";
import type {
  BulkGenerateResult,
  BulkPreview,
  BulkStatus,
  OxfordLoadResult,
  OxfordLoadStatus,
  ReadinessReport,
  Settings
} from "../types";

import { title } from "../utils/format";



export function SettingsView({
  readiness,
  onRefresh,
  onRefreshReadiness
}: {
  readiness: ReadinessReport | null;
  onRefresh: () => Promise<void>;
  onRefreshReadiness: () => Promise<ReadinessReport>;
}) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [oxfordStatus, setOxfordStatus] = useState<OxfordLoadStatus | null>(null);
  const [contentStatus, setContentStatus] = useState<BulkStatus | null>(null);
  const [audioStatus, setAudioStatus] = useState<BulkStatus | null>(null);
  const [preview, setPreview] = useState<{ kind: "content" | "audio"; data: BulkPreview } | null>(null);
  const [running, setRunning] = useState<"content" | "audio" | null>(null);
  const [loadingOxford, setLoadingOxford] = useState(false);
  const [oxfordResult, setOxfordResult] = useState<OxfordLoadResult | null>(null);
  const [results, setResults] = useState<Partial<Record<"content" | "audio", BulkGenerateResult>>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [checkingReadiness, setCheckingReadiness] = useState(false);

  async function load(selectedSettings?: Settings) {
    const activeSettings = selectedSettings ?? await getJson<Settings>("/settings");
    if (!selectedSettings) {
      setSettings(activeSettings);
    }
    setOxfordStatus(await getJson<OxfordLoadStatus>("/spelling/oxford/load-status"));
    setContentStatus(await getJson<BulkStatus>("/spelling/content/bulk-status"));
    const audioParams = new URLSearchParams({
      voice: activeSettings.tts_voice,
      model: activeSettings.tts_model
    });
    setAudioStatus(await getJson<BulkStatus>(`/spelling/audio/bulk-status?${audioParams.toString()}`));
    setSettingsError(null);
  }

  async function refreshEnvironment() {
    setCheckingReadiness(true);
    try {
      const report = await onRefreshReadiness();
      if (report.status === "unavailable") {
        setSettings(null);
        setSettingsError("Database-backed settings are unavailable until the required database checks pass.");
      } else if (!settings) {
        await load();
      }
    } catch (err) {
      setSettingsError(err instanceof Error ? err.message : "Environment readiness could not be checked.");
    } finally {
      setCheckingReadiness(false);
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    const updated = await patchJson<Settings>("/settings", settings);
    setSettings(updated);
    await load(updated);
    await onRefresh();
    setMessage("Settings saved.");
  }

  async function openPreview(kind: "content" | "audio") {
    if (!settings) return;
    const limit = Math.max(1, Math.min(settings.content_bulk_limit, 5000));
    const params = new URLSearchParams({ limit: String(limit) });
    if (kind === "audio") {
      params.set("voice", settings.tts_voice);
      params.set("model", settings.tts_model);
    }
    const path = kind === "content" ? "/spelling/content/bulk-preview" : "/spelling/audio/bulk-preview";
    const data = await getJson<BulkPreview>(`${path}?${params.toString()}`);
    setPreview({ kind, data });
    setMessage(null);
  }

  async function generate(kind: "content" | "audio") {
    if (!settings) return;
    const path = kind === "content" ? "/spelling/content/bulk-generate" : "/spelling/audio/bulk-generate";
    setRunning(kind);
    setMessage(null);
    try {
      const result = await postJson<BulkGenerateResult>(path, {
        limit: settings.content_bulk_limit,
        voice: settings.tts_voice,
        model: settings.tts_model
      });
      setResults((existing) => ({ ...existing, [kind]: result }));
      await load(settings);
      setPreview(null);
      setMessage(`${kind === "content" ? "Word learning content" : "Word audio"} batch finished.`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Generation failed.");
    } finally {
      setRunning(null);
    }
  }

  async function loadOxfordBatch() {
    if (!settings) return;
    setLoadingOxford(true);
    setMessage(null);
    try {
      const result = await postJson<OxfordLoadResult>("/spelling/oxford/load-batch", {
        limit: settings.content_bulk_limit
      });
      setOxfordResult(result);
      await load(settings);
      await onRefresh();
      setMessage(`Oxford import finished: ${result.created} loaded, ${result.updated} already existed.`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Oxford import failed.");
    } finally {
      setLoadingOxford(false);
    }
  }

  useEffect(() => {
    refreshEnvironment().catch(() => undefined);
  }, []);

  if (!settings) {
    return (
      <section className="panel full">
        <h1>Settings</h1>
        <EnvironmentReadiness
          report={readiness}
          refreshing={checkingReadiness}
          onRefresh={refreshEnvironment}
        />
        {settingsError ? <div className="banner error">{settingsError}</div> : null}
      </section>
    );
  }
  return (
    <section className="panel full">
      <h1>Settings</h1>
      <EnvironmentReadiness
        report={readiness}
        refreshing={checkingReadiness}
        onRefresh={refreshEnvironment}
      />
      <form className="settings-form" onSubmit={save}>
        <label>Theme
          <select value={settings.theme} onChange={(event) => setSettings({ ...settings, theme: event.target.value })}>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </label>
        <label>TTS Voice
          <select
            value={settings.tts_voice}
            onChange={(event) => {
              const updated = { ...settings, tts_voice: event.target.value };
              setSettings(updated);
              load(updated).catch(() => setAudioStatus(null));
            }}
          >
            {[
              "alloy",
              "ash",
              "ballad",
              "cedar",
              "coral",
              "echo",
              "fable",
              "marin",
              "nova",
              "onyx",
              "sage",
              "shimmer",
              "verse"
            ].map((voice) => (
              <option value={voice} key={voice}>{title(voice)}</option>
            ))}
          </select>
        </label>
        <label>Batch size
          <input type="number" min={1} max={5000} value={settings.content_bulk_limit} onChange={(event) => setSettings({ ...settings, content_bulk_limit: Number(event.target.value) })} />
          <small>Used for loading Oxford words, generating content, and generating audio. Development default is 100 words per run.</small>
        </label>
        <label>AI generation
          <select value={settings.ai_generation_enabled ? "enabled" : "disabled"} onChange={(event) => setSettings({ ...settings, ai_generation_enabled: event.target.value === "enabled" })}>
            <option value="enabled">Enabled</option>
            <option value="disabled">Disabled</option>
          </select>
        </label>
        <label>English standard
          <select
            value={settings.english_variant}
            onChange={(event) => setSettings({
              ...settings,
              english_variant: event.target.value as Settings["english_variant"]
            })}
          >
            <option value="en-GB">British English</option>
            <option value="en-US">American English</option>
          </select>
        </label>
        <label className="advanced-field">TTS Model
          <input
            value={settings.tts_model}
            onBlur={() => load(settings).catch(() => setAudioStatus(null))}
            onChange={(event) => {
              setAudioStatus(null);
              setSettings({ ...settings, tts_model: event.target.value });
            }}
          />
        </label>
        <label className="advanced-field">AI Model<input value={settings.ai_model} onChange={(event) => setSettings({ ...settings, ai_model: event.target.value })} /></label>
        <button>Save Settings</button>
      </form>

      <OxfordLoader
        status={oxfordStatus}
        batchSize={settings.content_bulk_limit}
        running={loadingOxford}
        result={oxfordResult}
        onLoad={loadOxfordBatch}
      />

      <div className="settings-section-head">
        <div>
          <p className="eyebrow">Advanced</p>
          <h2>Content & Audio Cache</h2>
          <p>Optional pre-generation for Oxford words. The app still works with on-demand content and audio.</p>
        </div>
      </div>
      <div className="bulk-grid">
        <BulkCard
          title="Word Learning Content"
          text="Generates cached meanings, IPA, examples, word family, and spelling help for Oxford words."
          status={contentStatus}
          result={results.content}
          running={running === "content"}
          oxfordStatus={oxfordStatus}
          onPreview={() => openPreview("content")}
        />
        <BulkCard
          title="Word Audio Cache"
          text="Generates cached OpenAI TTS files so Listen buttons are faster and more reliable."
          status={audioStatus}
          result={results.audio}
          running={running === "audio"}
          oxfordStatus={oxfordStatus}
          variant={{ voice: settings.tts_voice, model: settings.tts_model }}
          onPreview={() => openPreview("audio")}
        />
      </div>
      {message ? <div className="banner success">{message}</div> : null}
      {preview ? (
        <BulkPreviewPanel
          kind={preview.kind}
          preview={preview.data}
          running={running === preview.kind}
          onCancel={() => setPreview(null)}
          onConfirm={() => generate(preview.kind)}
        />
      ) : null}
    </section>
  );
}

function EnvironmentReadiness({
  report,
  refreshing,
  onRefresh
}: {
  report: ReadinessReport | null;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const summary = report?.status === "ready"
    ? "Environment ready"
    : report?.status === "degraded"
      ? "Optional setup needs attention"
      : report?.status === "unavailable"
        ? "Required service unavailable"
        : "Readiness not checked";

  return (
    <section className="readiness-section" aria-labelledby="readiness-heading">
      <div className="readiness-head">
        <div>
          <p className="eyebrow">Environment</p>
          <h2 id="readiness-heading">System Readiness</h2>
          <p>
            {summary}
            {report ? ` · ${report.database_target}` : ""}
          </p>
        </div>
        <button className="secondary" disabled={refreshing} onClick={onRefresh}>
          <RefreshCcw className={refreshing ? "spin" : undefined} size={16} />
          {refreshing ? "Checking" : "Refresh"}
        </button>
      </div>
      {report ? (
        <div className="readiness-list">
          {report.checks.map((check) => {
            const Icon = check.status === "ready" ? CheckCircle2 : check.status === "warning" ? AlertTriangle : XCircle;
            return (
              <div className={`readiness-row ${check.status}`} key={check.key}>
                <Icon size={20} />
                <div>
                  <strong>{check.label}</strong>
                  <p>{check.detail}</p>
                  {check.action ? <small><b>Next:</b> {check.action}</small> : null}
                </div>
                <span>{title(check.status)}</span>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="readiness-empty">The backend readiness report is unavailable.</div>
      )}
    </section>
  );
}

function OxfordLoader({
  status,
  batchSize,
  running,
  result,
  onLoad
}: {
  status: OxfordLoadStatus | null;
  batchSize: number;
  running: boolean;
  result: OxfordLoadResult | null;
  onLoad: () => void;
}) {
  const loaded = status?.loaded_words ?? 0;
  const target = status?.target_words ?? 5000;
  const remaining = status?.remaining_words ?? Math.max(target - loaded, 0);
  const canLoad = Boolean(status?.source_available && remaining > 0);

  return (
    <article className="oxford-loader">
      <div>
        <p className="eyebrow">Oxford 5K Loader</p>
        <h2>Load words before generating content or audio</h2>
        <p>
          Import the next batch from the local Oxford PDFs. This only loads word records and source ranks; AI content and audio stay manual.
        </p>
      </div>
      <div className="oxford-loader-grid">
        <span><b>{loaded}</b> loaded</span>
        <span><b>{target}</b> target</span>
        <span><b>{remaining}</b> remaining</span>
        <span><b>{status?.source_available ? "Ready" : "Missing"}</b> source PDFs</span>
      </div>
      {result ? (
        <div className="bulk-result">
          Last import: {result.created} loaded, {result.updated} already existed, {result.skipped} skipped, {result.remaining_words} remaining.
        </div>
      ) : null}
      <button disabled={running || !canLoad} onClick={onLoad}>
        {running ? <Loader2 className="spin" size={16} /> : null}
        {running ? "Loading Oxford words..." : `Load Next ${Math.max(1, Math.min(batchSize, 5000))} Oxford Words`}
      </button>
      {!status?.source_available ? <div className="banner warn">Oxford PDFs are missing from the data folder.</div> : null}
    </article>
  );
}

function BulkCard({
  title: cardTitle,
  text,
  status,
  result,
  running,
  oxfordStatus,
  variant,
  onPreview
}: {
  title: string;
  text: string;
  status: BulkStatus | null;
  result?: BulkGenerateResult;
  running: boolean;
  oxfordStatus: OxfordLoadStatus | null;
  variant?: { voice: string; model: string };
  onPreview: () => void;
}) {
  const pending = status?.pending ?? 0;
  const ready = (status?.generated ?? 0) + (status?.fallback ?? 0) + (status?.reviewed ?? 0);
  const loaded = oxfordStatus?.loaded_words ?? status?.total_words ?? 0;
  const target = oxfordStatus?.target_words ?? 5000;
  let buttonLabel = cardTitle.includes("Audio") ? "Preview Audio Batch" : "Preview Content Batch";
  if (!status) {
    buttonLabel = "Checking cache";
  } else if (pending === 0) {
    buttonLabel = loaded < target ? "Load More Oxford Words First" : "All Loaded Words Cached";
  }

  return (
    <article className="bulk-card">
      <h3>{cardTitle}</h3>
      <p>{text}</p>
      {variant ? (
        <div className="audio-cache-variant">
          <span><b>Voice</b>{title(variant.voice)}</span>
          <span><b>Model</b>{variant.model}</span>
          <span><b>Status</b>{status ? "Cache checked" : "Checking cache"}</span>
        </div>
      ) : null}
      <div className="bulk-status-row">
        <span><b>{ready} / {loaded}</b> ready / loaded</span>
        <span><b>{pending}</b> pending among loaded</span>
        <span><b>{status?.failed ?? 0}</b> failed</span>
      </div>
      {!variant && ((status?.fallback ?? 0) > 0 || (status?.reviewed ?? 0) > 0) ? (
        <div className="bulk-result">
          {status?.fallback ?? 0} deterministic fallback, {status?.reviewed ?? 0} manually reviewed.
        </div>
      ) : null}
      {result ? (
        <div className={result.failed ? "bulk-result warn" : "bulk-result"}>
          Last run: {result.generated} generated, {result.fallback ?? 0} fallback, {result.cached} cached, {result.failed} failed, {result.remaining} remaining.
        </div>
      ) : null}
      <button disabled={running || !status || pending === 0} onClick={onPreview}>
        {running ? <Loader2 className="spin" size={16} /> : null}
        {running ? "Generating..." : buttonLabel}
      </button>
    </article>
  );
}

function BulkPreviewPanel({
  kind,
  preview,
  running,
  onCancel,
  onConfirm
}: {
  kind: "content" | "audio";
  preview: BulkPreview;
  running: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <article className="bulk-preview-modal">
        <div className="section-head">
          <div>
            <p className="eyebrow">Confirm Batch</p>
            <h2>{kind === "content" ? "Generate word learning content" : "Generate word audio cache"}</h2>
          </div>
          <button className="secondary" disabled={running} onClick={onCancel}>Cancel</button>
        </div>
        <p>
          This will process up to {preview.will_process} words from a batch size of {preview.limit}.
          {kind === "content" && preview.ai_generation_enabled === false
            ? " AI generation is disabled, so deterministic fallback content will be saved without API calls."
            : " This may use OpenAI API quota."}
        </p>
        <div className="preview-grid">
          <span><b>{preview.total_words}</b>Total words</span>
          <span><b>{preview.generated}</b>Generated</span>
          {kind === "content" ? <span><b>{preview.fallback ?? 0}</b>Fallback</span> : null}
          {kind === "content" ? <span><b>{preview.reviewed ?? 0}</b>Reviewed</span> : null}
          <span><b>{preview.pending}</b>Pending</span>
          <span><b>{preview.failed}</b>Failed</span>
          <span><b>{preview.will_process}</b>Will process</span>
          <span><b>{preview.estimated_api_calls}</b>Est. API calls</span>
        </div>
        <div className="model-note">
          <strong>Model</strong>
          <span>{preview.model}</span>
          {preview.voice ? <><strong>Voice</strong><span>{preview.voice}</span></> : null}
        </div>
        {preview.failed ? <div className="banner warn">{preview.failed} previous failures are recorded. Retry after checking model, voice, and API key settings.</div> : null}
        <div className="action-row">
          <button className="secondary" disabled={running} onClick={onCancel}>Cancel</button>
          <button disabled={running || preview.will_process === 0} onClick={onConfirm}>
            {running ? <Loader2 className="spin" size={16} /> : null}
            {running ? "Generating..." : "Generate batch"}
          </button>
        </div>
      </article>
    </div>
  );
}
