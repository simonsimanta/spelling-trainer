import {
  Archive,
  BookOpen,
  Plus,
  RotateCcw,
  Sparkles,
  Trash2,
  X
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { deleteJson, getJson, patchJson, postJson } from "../api";
import type {
  DictationAdaptationResult,
  DictationText,
  DictationTextList
} from "../types";

type LibraryLevel = "all" | "sentence" | "passage" | "paragraph";

const levels: Array<{ key: LibraryLevel; label: string }> = [
  { key: "all", label: "All" },
  { key: "sentence", label: "Sentences" },
  { key: "passage", label: "Passages" },
  { key: "paragraph", label: "Paragraphs" }
];

function sourceLabel(item: DictationText): string {
  if (item.source_type === "personal") return "Personal";
  if (item.source_type === "ai_adapted") return "AI adapted";
  return "Reviewed built-in";
}

export function DictationLibrary() {
  const [library, setLibrary] = useState<DictationTextList | null>(null);
  const [level, setLevel] = useState<LibraryLevel>("all");
  const [showImport, setShowImport] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [targets, setTargets] = useState("");
  const [importLevel, setImportLevel] = useState<"auto" | "sentence" | "passage" | "paragraph">("auto");
  const [busyId, setBusyId] = useState<number | "create" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadLibrary() {
    const data = await getJson<DictationTextList>("/spelling/dictation/texts?status=all");
    setLibrary(data);
  }

  useEffect(() => {
    loadLibrary().catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to load dictation texts."));
  }, []);

  const items = useMemo(
    () => (library?.items ?? []).filter((item) => level === "all" || item.level === level),
    [library, level]
  );

  async function submitImport(event: FormEvent) {
    event.preventDefault();
    if (!title.trim() || !content.trim()) return;
    setBusyId("create");
    setError(null);
    setNotice(null);
    try {
      const created = await postJson<DictationText>("/spelling/dictation/texts", {
        title,
        content,
        level: importLevel,
        target_terms: targets.split(",").map((term) => term.trim()).filter(Boolean),
        allow_ai_adaptation: true
      });
      setTitle("");
      setContent("");
      setTargets("");
      setImportLevel("auto");
      setShowImport(false);
      setNotice(created.status === "reviewed" ? "Personal text added." : "Text added and marked for adaptation.");
      await loadLibrary();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to add the text.");
    } finally {
      setBusyId(null);
    }
  }

  async function changeStatus(item: DictationText) {
    setBusyId(item.id);
    setError(null);
    try {
      await patchJson(`/spelling/dictation/texts/${item.id}`, {
        action: item.status === "archived" ? "restore" : "archive"
      });
      await loadLibrary();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to update the text.");
    } finally {
      setBusyId(null);
    }
  }

  async function remove(item: DictationText) {
    setBusyId(item.id);
    setError(null);
    try {
      await deleteJson(`/spelling/dictation/texts/${item.id}`);
      setNotice("Personal text deleted.");
      await loadLibrary();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to delete the text.");
    } finally {
      setBusyId(null);
    }
  }

  async function adapt(item: DictationText) {
    setBusyId(item.id);
    setError(null);
    setNotice(null);
    try {
      const result = await postJson<DictationAdaptationResult>(`/spelling/dictation/texts/${item.id}/adapt`, {
        level: item.level,
        target_terms: item.targets.map((target) => target.term)
      });
      setNotice(
        result.used_fallback
          ? `Reviewed fallback selected: ${result.text.title}. ${result.fallback_reason ?? ""}`.trim()
          : result.cached
          ? `Cached adaptation ready: ${result.text.title}.`
          : `Adaptation added: ${result.text.title}.`
      );
      await loadLibrary();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to adapt the text.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="dictation-library" aria-labelledby="dictation-library-title">
      <header className="section-head">
        <div>
          <p className="eyebrow">Content</p>
          <h2 id="dictation-library-title">Text library</h2>
        </div>
        <button className="secondary" onClick={() => setShowImport((value) => !value)}>
          {showImport ? <X size={17} /> : <Plus size={17} />}
          {showImport ? "Close" : "Add personal text"}
        </button>
      </header>

      {showImport ? (
        <form className="dictation-import" onSubmit={submitImport}>
          <label>
            Title
            <input maxLength={160} required value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label>
            Level
            <select value={importLevel} onChange={(event) => setImportLevel(event.target.value as typeof importLevel)}>
              <option value="auto">Automatic</option>
              <option value="sentence">Sentence</option>
              <option value="passage">Passage</option>
              <option value="paragraph">Paragraph</option>
            </select>
          </label>
          <label className="dictation-import-wide">
            Text
            <textarea maxLength={10000} required value={content} onChange={(event) => setContent(event.target.value)} />
          </label>
          <label className="dictation-import-wide">
            Target spellings
            <input placeholder="necessary, separate" value={targets} onChange={(event) => setTargets(event.target.value)} />
          </label>
          <button disabled={busyId === "create"} type="submit">
            <Plus size={17} /> Add text
          </button>
        </form>
      ) : null}

      <div className="dictation-level-tabs" role="tablist" aria-label="Dictation text level">
        {levels.map((item) => (
          <button
            className={level === item.key ? "active" : "secondary"}
            key={item.key}
            onClick={() => setLevel(item.key)}
            role="tab"
            aria-selected={level === item.key}
          >
            {item.label}
            <span>{item.key === "all" ? library?.total ?? 0 : library?.counts[item.key] ?? 0}</span>
          </button>
        ))}
      </div>

      {error ? <div className="banner error">{error}</div> : null}
      {notice ? <div className="banner success">{notice}</div> : null}

      <div className="dictation-text-list">
        {items.map((item) => (
          <article className={item.status === "archived" ? "archived" : ""} key={item.id}>
            <div className="dictation-text-icon"><BookOpen size={19} /></div>
            <div className="dictation-text-copy">
              <div>
                <h3>{item.title}</h3>
                <span>{sourceLabel(item)}</span>
              </div>
              <p>{item.word_count} words / {item.sentence_count} {item.sentence_count === 1 ? "sentence" : "sentences"} / {item.target_count} targets</p>
              {item.source_type === "personal" && item.content ? <blockquote>{item.content}</blockquote> : null}
              {item.quality_warnings.length ? <small>{item.quality_warnings.join(" ")}</small> : null}
            </div>
            <div className="dictation-text-actions">
              {item.source_type !== "curated" && item.allow_ai_adaptation && item.status !== "archived" ? (
                <button className="secondary" disabled={busyId === item.id} onClick={() => adapt(item)}>
                  <Sparkles size={16} /> Adapt
                </button>
              ) : null}
              {item.source_type !== "curated" ? (
                <button
                  className="icon-button"
                  disabled={busyId === item.id}
                  onClick={() => changeStatus(item)}
                  aria-label={item.status === "archived" ? `Restore ${item.title}` : `Archive ${item.title}`}
                  title={item.status === "archived" ? "Restore" : "Archive"}
                >
                  {item.status === "archived" ? <RotateCcw size={17} /> : <Archive size={17} />}
                </button>
              ) : null}
              {item.source_type !== "curated" && item.use_count === 0 ? (
                <button
                  className="icon-button danger-icon"
                  disabled={busyId === item.id}
                  onClick={() => remove(item)}
                  aria-label={`Delete ${item.title}`}
                  title="Delete"
                >
                  <Trash2 size={17} />
                </button>
              ) : null}
            </div>
          </article>
        ))}
        {!items.length ? <p className="empty-copy">No texts match this level.</p> : null}
      </div>
    </section>
  );
}
