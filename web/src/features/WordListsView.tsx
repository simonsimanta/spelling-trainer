import {
  Archive as ArchiveIcon,
  ArchiveRestore,
  ArrowUpDown,
  BookOpenCheck,
  Check,
  ChevronLeft,
  ChevronRight,
  Pencil,
  Play,
  RotateCcw,
  Search,
  Volume2,
  X
} from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { getJson, patchJson, playWordAudio, postJson } from "../api";
import type {
  ManagedWord,
  SpellingSuggestion,
  Word,
  WordContent,
  WordManagementCounts,
  WordManagementPage
} from "../types";

import { title } from "../utils/format";



const emptyWordCounts: WordManagementCounts = {
  all: 0,
  oxford: 0,
  personal: 0,
  suggested: 0,
  trouble: 0,
  provisional: 0,
  stable: 0,
  seed: 0,
  archived: 0
};

const wordCategories: Array<{ key: keyof WordManagementCounts; label: string }> = [
  { key: "all", label: "All active" },
  { key: "oxford", label: "Oxford" },
  { key: "personal", label: "Personal" },
  { key: "suggested", label: "Suggested" },
  { key: "trouble", label: "Trouble" },
  { key: "provisional", label: "Provisional" },
  { key: "stable", label: "Stable" },
  { key: "seed", label: "Starter" },
  { key: "archived", label: "Archived" }
];

type WordActionResult = {
  word_id: number;
  term: string;
  action: string;
  message: string;
};

type WordEditDraft = {
  term: string;
  short_meaning: string;
  example_sentence: string;
  part_of_speech: string;
  cefr_level: string;
};

type ContentReviewDraft = {
  meaning: string;
  ipa: string;
  part_of_speech: string;
  examples: string;
  word_family: string;
  chunked_form: string;
  mnemonic: string;
  phonetic_hint: string;
  review_notes: string;
};

function contentReviewDraft(content: WordContent): ContentReviewDraft {
  return {
    meaning: content.meaning,
    ipa: content.ipa ?? "",
    part_of_speech: content.part_of_speech ?? "",
    examples: content.examples.join("\n"),
    word_family: content.word_family.map((item) => `${item.term} | ${item.label}`).join("\n"),
    chunked_form: content.chunked_form ?? "",
    mnemonic: content.mnemonic ?? "",
    phonetic_hint: content.phonetic_hint ?? "",
    review_notes: content.review_notes ?? ""
  };
}

function parseWordFamily(value: string): Array<{ term: string; label: string }> {
  return value.split("\n").map((line) => {
    const [term, label] = line.split("|").map((item) => item.trim());
    return { term, label: label || "related" };
  }).filter((item) => item.term);
}

function displayDate(value?: string | null): string {
  if (!value) return "Never";
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" }).format(new Date(value));
}

export function WordListsView({
  onPractice,
  onRefresh
}: {
  onPractice: (wordId: number) => Promise<void>;
  onRefresh: () => Promise<void>;
}) {
  const [category, setCategory] = useState<keyof WordManagementCounts>("all");
  const [page, setPage] = useState<WordManagementPage>({
    items: [],
    total: 0,
    counts: emptyWordCounts
  });
  const [suggestions, setSuggestions] = useState<SpellingSuggestion[]>([]);
  const [newWord, setNewWord] = useState("");
  const [searchDraft, setSearchDraft] = useState("");
  const [query, setQuery] = useState("");
  const [masteryState, setMasteryState] = useState("all");
  const [diagnosticStatus, setDiagnosticStatus] = useState("all");
  const [sort, setSort] = useState("term");
  const [direction, setDirection] = useState<"asc" | "desc">("asc");
  const [offset, setOffset] = useState(0);
  const [loadingWords, setLoadingWords] = useState(true);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [editing, setEditing] = useState<ManagedWord | null>(null);
  const [editDraft, setEditDraft] = useState<WordEditDraft | null>(null);
  const [reviewing, setReviewing] = useState<ManagedWord | null>(null);
  const [reviewContent, setReviewContent] = useState<WordContent | null>(null);
  const [reviewDraft, setReviewDraft] = useState<ContentReviewDraft | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const limit = 50;

  async function load() {
    const params = new URLSearchParams({
      category,
      sort,
      direction,
      limit: String(limit),
      offset: String(offset)
    });
    if (query) params.set("query", query);
    if (masteryState !== "all") params.set("mastery_state", masteryState);
    if (diagnosticStatus !== "all") params.set("diagnostic_status", diagnosticStatus);
    setLoadingWords(true);
    try {
      const [nextPage, pendingSuggestions] = await Promise.all([
        getJson<WordManagementPage>(`/spelling/word-management?${params.toString()}`),
        getJson<SpellingSuggestion[]>("/spelling/suggestions?status=pending")
      ]);
      setPage(nextPage);
      setSuggestions(pendingSuggestions);
      setListError(null);
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Unable to load words.");
    } finally {
      setLoadingWords(false);
    }
  }

  useEffect(() => {
    load().catch(() => undefined);
  }, [category, query, masteryState, diagnosticStatus, sort, direction, offset]);

  async function addWord(event: FormEvent) {
    event.preventDefault();
    if (!newWord.trim()) return;
    try {
      const created = await postJson<Word>("/spelling/words", {
        term: newWord,
        level: "personal",
        source: "manual"
      });
      setNewWord("");
      setCategory("personal");
      setSearchDraft(created.term);
      setQuery(created.term);
      setOffset(0);
      setFeedback(`${title(created.term)} was added to Personal words.`);
      setListError(null);
      await onRefresh();
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Unable to add this word.");
    }
  }

  function openEditor(word: ManagedWord) {
    setEditing(word);
    setEditDraft({
      term: word.term,
      short_meaning: word.short_meaning ?? "",
      example_sentence: word.example_sentence ?? "",
      part_of_speech: word.part_of_speech ?? "",
      cefr_level: word.cefr_level ?? ""
    });
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (!editing || !editDraft) return;
    try {
      const updated = await patchJson<Word>(`/spelling/words/${editing.id}`, editDraft);
      setEditing(null);
      setEditDraft(null);
      setFeedback(`${title(updated.term)} was updated.`);
      setListError(null);
      await load();
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Unable to update this word.");
    }
  }

  async function openContentReview(word: ManagedWord) {
    setReviewing(word);
    setReviewContent(null);
    setReviewDraft(null);
    setReviewError(null);
    setReviewBusy(true);
    try {
      const content = await getJson<WordContent>(`/spelling/word-content/${word.id}`);
      setReviewContent(content);
      setReviewDraft(contentReviewDraft(content));
      setListError(null);
    } catch (err) {
      setReviewing(null);
      setListError(err instanceof Error ? err.message : "Unable to load this word's content.");
    } finally {
      setReviewBusy(false);
    }
  }

  function closeContentReview() {
    setReviewing(null);
    setReviewContent(null);
    setReviewDraft(null);
    setReviewError(null);
  }

  async function saveContentReview(testAudio: boolean) {
    if (!reviewing || !reviewDraft) return;
    setReviewBusy(true);
    try {
      const updated = await patchJson<WordContent>(`/spelling/word-content/${reviewing.id}`, {
        ...reviewDraft,
        examples: reviewDraft.examples.split("\n").map((item) => item.trim()).filter(Boolean),
        word_family: parseWordFamily(reviewDraft.word_family)
      });
      setReviewContent(updated);
      setReviewDraft(contentReviewDraft(updated));
      setFeedback(`${title(reviewing.term)} content was reviewed and saved.`);
      setReviewError(null);
      setListError(null);
      if (testAudio) {
        await playWordAudio(reviewing.id, true);
      } else {
        closeContentReview();
      }
      await load();
    } catch (err) {
      setReviewError(err instanceof Error ? err.message : "Unable to save this content review.");
    } finally {
      setReviewBusy(false);
    }
  }

  async function applyWordAction(word: ManagedWord, action: WordActionResult["action"]) {
    if (action === "reset" && !window.confirm(`Reset all learning progress for "${word.term}"?`)) return;
    try {
      const result = await postJson<WordActionResult>(`/spelling/words/${word.id}/actions`, { action });
      setFeedback(result.message);
      setListError(null);
      if (action === "practice") {
        await onPractice(word.id);
        return;
      }
      await Promise.all([load(), onRefresh()]);
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Unable to update this word.");
    }
  }

  async function reviewSuggestion(suggestionId: number, status: "approved" | "rejected") {
    try {
      const updated = await patchJson<SpellingSuggestion>(`/spelling/suggestions/${suggestionId}`, { status });
      setFeedback(`${title(updated.term)} was ${status}.`);
      await Promise.all([load(), onRefresh()]);
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Unable to review this suggestion.");
    }
  }

  function applySearch(event: FormEvent) {
    event.preventDefault();
    setQuery(searchDraft.trim());
    setOffset(0);
  }

  function resetFilters() {
    setSearchDraft("");
    setQuery("");
    setMasteryState("all");
    setDiagnosticStatus("all");
    setSort("term");
    setDirection("asc");
    setOffset(0);
  }

  const rangeStart = page.total ? offset + 1 : 0;
  const rangeEnd = Math.min(offset + limit, page.total);

  return (
    <section className="word-management">
      <div className="section-head word-management-head">
        <div>
          <p className="eyebrow">Library</p>
          <h1>Word Lists</h1>
          <p className="muted">Search your vocabulary, inspect its learning state, and decide what happens next.</p>
        </div>
        <form className="inline-form word-add-form" onSubmit={addWord}>
          <input
            aria-label="New personal word"
            value={newWord}
            onChange={(event) => setNewWord(event.target.value)}
            placeholder="Add personal word"
          />
          <button>Add word</button>
        </form>
      </div>

      {feedback ? (
        <div className="banner success word-feedback" role="status">
          <span>{feedback}</span>
          <button className="icon-button compact" aria-label="Dismiss message" title="Dismiss" onClick={() => setFeedback(null)}>
            <X size={16} />
          </button>
        </div>
      ) : null}
      {listError ? <div className="banner error" role="alert">{listError}</div> : null}

      <div className="word-category-tabs" role="tablist" aria-label="Word categories">
        {wordCategories.map((item) => (
          <button
            role="tab"
            aria-selected={category === item.key}
            className={category === item.key ? "active" : ""}
            key={item.key}
            onClick={() => {
              setCategory(item.key);
              setOffset(0);
            }}
          >
            <span>{item.label}</span>
            <strong>{page.counts[item.key]}</strong>
          </button>
        ))}
      </div>

      <div className="word-list-toolbar">
        <form className="word-search" onSubmit={applySearch}>
          <Search size={18} />
          <input
            aria-label="Search words"
            value={searchDraft}
            onChange={(event) => setSearchDraft(event.target.value)}
            placeholder="Search word or meaning"
          />
          <button aria-label="Run search" title="Search"><Search size={17} /></button>
        </form>
        <label>
          <span>Mastery</span>
          <select value={masteryState} onChange={(event) => {
            setMasteryState(event.target.value);
            setOffset(0);
          }}>
            <option value="all">All states</option>
            <option value="new">New</option>
            <option value="learning">Learning</option>
            <option value="review">Review</option>
            <option value="known_provisional">Provisional</option>
            <option value="stable_known">Stable</option>
            <option value="lapse">Lapse</option>
            <option value="known">Known</option>
          </select>
        </label>
        <label>
          <span>Diagnostic</span>
          <select value={diagnosticStatus} onChange={(event) => {
            setDiagnosticStatus(event.target.value);
            setOffset(0);
          }}>
            <option value="all">All results</option>
            <option value="untested">Untested</option>
            <option value="passed">Passed</option>
            <option value="missed">Missed</option>
          </select>
        </label>
        <label>
          <span>Sort</span>
          <select value={sort} onChange={(event) => {
            setSort(event.target.value);
            setOffset(0);
          }}>
            <option value="term">Word</option>
            <option value="frequency_rank">Frequency rank</option>
            <option value="due_date">Due date</option>
            <option value="last_attempt">Last attempt</option>
            <option value="priority">Practice priority</option>
          </select>
        </label>
        <button
          className="icon-button toolbar-icon"
          aria-label={`Sort ${direction === "asc" ? "descending" : "ascending"}`}
          title={`Sort ${direction === "asc" ? "descending" : "ascending"}`}
          onClick={() => setDirection((current) => current === "asc" ? "desc" : "asc")}
        >
          <ArrowUpDown size={18} />
        </button>
        <button className="secondary toolbar-reset" onClick={resetFilters}>
          <RotateCcw size={17} /> Reset
        </button>
      </div>

      {category === "suggested" && suggestions.length ? (
        <section className="suggestion-review" aria-labelledby="pending-suggestions-title">
          <div>
            <p className="eyebrow">Review queue</p>
            <h2 id="pending-suggestions-title">Pending suggestions</h2>
          </div>
          <div className="suggestion-rows">
            {suggestions.map((suggestion) => (
              <article key={suggestion.id}>
                <div>
                  <strong>{suggestion.term}</strong>
                  <span>{suggestion.reason}</span>
                </div>
                <div className="suggestion-actions">
                  <button onClick={() => reviewSuggestion(suggestion.id, "approved")}>
                    <Check size={17} /> Approve
                  </button>
                  <button className="secondary" onClick={() => reviewSuggestion(suggestion.id, "rejected")}>
                    <X size={17} /> Reject
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <div className="word-list-summary">
        <span>{loadingWords ? "Loading words..." : `Showing ${rangeStart}-${rangeEnd} of ${page.total}`}</span>
        {(query || masteryState !== "all" || diagnosticStatus !== "all") ? <strong>Filtered</strong> : null}
      </div>

      <div className="word-management-table-wrap">
        <table className="word-management-table">
          <thead>
            <tr>
              <th>Word</th>
              <th>Source</th>
              <th>Level</th>
              <th>Learning state</th>
              <th>Schedule</th>
              <th>Last attempt</th>
              <th><span className="visually-hidden">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {!loadingWords && !page.items.length ? (
              <tr>
                <td className="word-list-empty" colSpan={7}>
                  <Search size={26} />
                  <strong>No matching words</strong>
                  <span>Change the category or clear the filters.</span>
                </td>
              </tr>
            ) : page.items.map((word) => (
              <tr key={word.id}>
                <td data-label="Word">
                  <strong className="word-term">{word.term}</strong>
                  <span className="word-meaning">{word.short_meaning ?? word.example_sentence ?? "No meaning added"}</span>
                </td>
                <td data-label="Source">
                  <span className="status-pill neutral">{word.source_label}</span>
                  {word.source_list ? <small>{word.source_list.replace(/_/g, " ")}</small> : null}
                </td>
                <td data-label="Level">
                  <strong>{word.cefr_level ?? title(word.level)}</strong>
                  <small>{word.frequency_rank ? `Rank ${word.frequency_rank.toLocaleString()}` : "No rank"}</small>
                </td>
                <td data-label="Learning state">
                  <span className={`status-pill ${word.mastery_state === "lapse" || word.mastery_state === "trouble" ? "danger" : "learning"}`}>
                    {title(word.mastery_state)}
                  </span>
                  <small>Diagnostic: {title(word.diagnostic_status)}</small>
                </td>
                <td data-label="Schedule">
                  <strong>{word.due_date ? displayDate(word.due_date) : "Not scheduled"}</strong>
                  <small>{word.review_stage ? title(word.review_stage) : "No review stage"}</small>
                </td>
                <td data-label="Last attempt">
                  <strong>{displayDate(word.last_attempt_at)}</strong>
                  {word.last_attempt_correct === true ? <small className="correct-text">Correct</small> : null}
                  {word.last_attempt_correct === false ? <small className="incorrect-text">Missed</small> : null}
                </td>
                <td className="word-row-actions">
                  {word.is_active ? (
                    <>
                      <button className="icon-button compact" aria-label={`Practice ${word.term}`} title="Practice now" onClick={() => applyWordAction(word, "practice")}>
                        <Play size={16} />
                      </button>
                      <button className="icon-button compact" aria-label={`Mark ${word.term} known`} title="Mark known" onClick={() => applyWordAction(word, "mark_known")}>
                        <Check size={16} />
                      </button>
                      <button className="icon-button compact" aria-label={`Reset ${word.term}`} title="Reset learning progress" onClick={() => applyWordAction(word, "reset")}>
                        <RotateCcw size={16} />
                      </button>
                      <button className="icon-button compact" aria-label={`Review content for ${word.term}`} title="Review content and pronunciation" onClick={() => openContentReview(word)}>
                        <BookOpenCheck size={16} />
                      </button>
                      {word.is_personal ? (
                        <button className="icon-button compact" aria-label={`Edit ${word.term}`} title="Edit personal word" onClick={() => openEditor(word)}>
                          <Pencil size={16} />
                        </button>
                      ) : null}
                      <button className="icon-button compact danger-button" aria-label={`Archive ${word.term}`} title="Archive" onClick={() => applyWordAction(word, "archive")}>
                        <ArchiveIcon size={16} />
                      </button>
                    </>
                  ) : (
                    <button className="secondary" onClick={() => applyWordAction(word, "restore")}>
                      <ArchiveRestore size={17} /> Restore
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="word-pagination">
        <button className="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(offset - limit, 0))}>
          <ChevronLeft size={17} /> Previous
        </button>
        <span>{rangeStart}-{rangeEnd} of {page.total}</span>
        <button className="secondary" disabled={offset + limit >= page.total} onClick={() => setOffset(offset + limit)}>
          Next <ChevronRight size={17} />
        </button>
      </div>

      {editing && editDraft ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.currentTarget === event.target) {
            setEditing(null);
            setEditDraft(null);
          }
        }}>
          <section className="word-edit-modal" role="dialog" aria-modal="true" aria-labelledby="edit-word-title">
            <div className="section-head">
              <div>
                <p className="eyebrow">Personal word</p>
                <h2 id="edit-word-title">Edit {editing.term}</h2>
              </div>
              <button className="icon-button compact" aria-label="Close editor" title="Close" onClick={() => {
                setEditing(null);
                setEditDraft(null);
              }}>
                <X size={18} />
              </button>
            </div>
            <form className="word-edit-form" onSubmit={saveEdit}>
              <label>
                <span>Word</span>
                <input value={editDraft.term} onChange={(event) => setEditDraft({ ...editDraft, term: event.target.value })} required />
              </label>
              <div className="word-edit-grid">
                <label>
                  <span>Part of speech</span>
                  <input value={editDraft.part_of_speech} onChange={(event) => setEditDraft({ ...editDraft, part_of_speech: event.target.value })} />
                </label>
                <label>
                  <span>CEFR level</span>
                  <select value={editDraft.cefr_level} onChange={(event) => setEditDraft({ ...editDraft, cefr_level: event.target.value })}>
                    <option value="">Not set</option>
                    {["A1", "A2", "B1", "B2", "C1", "C2"].map((level) => <option key={level}>{level}</option>)}
                  </select>
                </label>
              </div>
              <label>
                <span>Meaning</span>
                <textarea value={editDraft.short_meaning} onChange={(event) => setEditDraft({ ...editDraft, short_meaning: event.target.value })} />
              </label>
              <label>
                <span>Example sentence</span>
                <textarea value={editDraft.example_sentence} onChange={(event) => setEditDraft({ ...editDraft, example_sentence: event.target.value })} />
              </label>
              <div className="modal-actions">
                <button type="button" className="secondary" onClick={() => {
                  setEditing(null);
                  setEditDraft(null);
                }}>Cancel</button>
                <button>Save changes</button>
              </div>
            </form>
          </section>
        </div>
      ) : null}

      {reviewing ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.currentTarget === event.target && !reviewBusy) closeContentReview();
        }}>
          <section className="word-edit-modal content-review-modal" role="dialog" aria-modal="true" aria-labelledby="content-review-title">
            <div className="section-head">
              <div>
                <p className="eyebrow">Content and pronunciation</p>
                <h2 id="content-review-title">Review {reviewing.term}</h2>
              </div>
              <button className="icon-button compact" aria-label="Close content review" title="Close" disabled={reviewBusy} onClick={closeContentReview}>
                <X size={18} />
              </button>
            </div>
            {reviewBusy && !reviewDraft ? <div className="content-review-loading">Loading content...</div> : null}
            {reviewDraft ? (
              <form className="word-edit-form" onSubmit={(event) => {
                event.preventDefault();
                saveContentReview(false).catch(() => undefined);
              }}>
                {reviewContent ? (
                  <div className={`content-source-banner ${reviewContent.generation_source}`}>
                    <strong>{reviewContent.generation_source === "ai" ? "AI generated" : reviewContent.generation_source === "manual" ? "Manually reviewed" : "Deterministic fallback"}</strong>
                    {reviewContent.fallback_reason ? <span>{reviewContent.fallback_reason}</span> : null}
                  </div>
                ) : null}
                {reviewError ? <div className="banner error" role="alert">{reviewError}</div> : null}
                <div className="word-edit-grid content-review-grid">
                  <label>
                    <span>Part of speech</span>
                    <input value={reviewDraft.part_of_speech} onChange={(event) => setReviewDraft({ ...reviewDraft, part_of_speech: event.target.value })} />
                  </label>
                  <label>
                    <span>IPA pronunciation</span>
                    <input value={reviewDraft.ipa} onChange={(event) => setReviewDraft({ ...reviewDraft, ipa: event.target.value })} placeholder="/pronunciation/" />
                  </label>
                </div>
                <label>
                  <span>Meaning</span>
                  <textarea value={reviewDraft.meaning} onChange={(event) => setReviewDraft({ ...reviewDraft, meaning: event.target.value })} required />
                </label>
                <label>
                  <span>Examples, one per line</span>
                  <textarea value={reviewDraft.examples} onChange={(event) => setReviewDraft({ ...reviewDraft, examples: event.target.value })} required />
                </label>
                <div className="word-edit-grid content-review-grid">
                  <label>
                    <span>Spelling chunks</span>
                    <input value={reviewDraft.chunked_form} onChange={(event) => setReviewDraft({ ...reviewDraft, chunked_form: event.target.value })} />
                  </label>
                  <label>
                    <span>Pronunciation hint</span>
                    <input value={reviewDraft.phonetic_hint} onChange={(event) => setReviewDraft({ ...reviewDraft, phonetic_hint: event.target.value })} placeholder="Stress or sound guidance" />
                  </label>
                </div>
                <label>
                  <span>Mnemonic</span>
                  <textarea value={reviewDraft.mnemonic} onChange={(event) => setReviewDraft({ ...reviewDraft, mnemonic: event.target.value })} />
                </label>
                <label>
                  <span>Word family, one "word | type" per line</span>
                  <textarea value={reviewDraft.word_family} onChange={(event) => setReviewDraft({ ...reviewDraft, word_family: event.target.value })} />
                </label>
                <label>
                  <span>Review notes</span>
                  <textarea value={reviewDraft.review_notes} onChange={(event) => setReviewDraft({ ...reviewDraft, review_notes: event.target.value })} />
                </label>
                <div className="modal-actions content-review-actions">
                  <button type="button" className="secondary" disabled={reviewBusy} onClick={closeContentReview}>Cancel</button>
                  <button type="button" className="secondary" disabled={reviewBusy} onClick={() => saveContentReview(true)}>
                    <Volume2 size={17} /> Save &amp; test audio
                  </button>
                  <button disabled={reviewBusy}>{reviewBusy ? "Saving..." : "Save review"}</button>
                </div>
              </form>
            ) : null}
          </section>
        </div>
      ) : null}
    </section>
  );
}
