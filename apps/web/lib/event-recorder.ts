/**
 * Event Recorder — captures user interactions in the web app as
 * structured, privacy-safe events. Runs entirely client-side until the
 * user explicitly ingests a session via the ingestion page.
 *
 * Key behaviours:
 *   - Opt-in: only captures once the user presses Record.
 *   - Persistent: the active session is mirrored to localStorage every
 *     second and on every `beforeunload`/`pagehide`, so the user can close
 *     the tab / navigate away / crash and still recover their events.
 *   - Auto-resumes on page reload while recording is active.
 *   - Captures explicit `web.page_exit` events whenever the user leaves
 *     the tab so the resulting context shows where the session stopped.
 *
 * Privacy contract:
 *   - Never captures input VALUES (only field names / types).
 *   - Never captures from password fields or [data-sensitive] elements.
 *   - Never captures from .sensitive elements or children of [data-sensitive].
 *   - Redacts long token-looking strings (>=24 alnum chars) from captured text.
 */

export type WebSessionEventType =
  | "web.click"
  | "web.navigation"
  | "web.form.submit"
  | "web.input.change"
  | "web.visibility"
  | "web.page_exit"
  | "web.page_resume"
  | "web.scroll.milestone";

export interface WebSessionEvent {
  id: string;
  type: WebSessionEventType;
  source: "web_recorder";
  timestamp: string;
  sequence: number;
  page_path: string;
  target: {
    tag?: string;
    role?: string;
    text?: string;
    selector?: string;
    href?: string;
    name?: string;
    input_type?: string;
  };
  metadata?: Record<string, unknown>;
}

export interface RecordingSession {
  session_id: string;
  title: string;
  description?: string;
  started_at: string;
  ended_at: string;
  duration_seconds: number;
  events: WebSessionEvent[];
  event_count: number;
  pages_visited: string[];
  ingested: boolean;
  ingested_at?: string;
  ingested_document_id?: string;
}

const MAX_EVENTS = 2000; // large ceiling — we persist across unloads
const MAX_TEXT_LEN = 120;
const TOKEN_LIKE_RE = /\b[a-zA-Z0-9_\-]{24,}\b/g;
const DEFAULT_MAX_DURATION_MINUTES = 120; // 2h cap
const ACTIVE_SESSION_KEY = "mycelium.active-recording.v1";
const AUTOSAVE_INTERVAL_MS = 2000;

type Listener = (status: RecorderStatus, session: RecordingSession | null) => void;

export type RecorderStatus = "idle" | "recording" | "stopped";

interface PersistedActive {
  session_id: string;
  started_at_ms: number;
  sequence: number;
  events: WebSessionEvent[];
  last_path: string;
}

/**
 * Browser-only class; guarded by `typeof window` checks so it can be
 * imported during SSR.
 */
export class EventRecorder {
  private events: WebSessionEvent[] = [];
  private sessionId = "";
  private startTime = 0;
  private sequence = 0;
  private status: RecorderStatus = "idle";
  private cleanupFns: Array<() => void> = [];
  private lastPath = "";
  private listeners = new Set<Listener>();
  private autoStopTimer: ReturnType<typeof setTimeout> | null = null;
  private autoSaveTimer: ReturnType<typeof setInterval> | null = null;
  private maxDurationMinutes = DEFAULT_MAX_DURATION_MINUTES;

  constructor() {
    if (typeof window !== "undefined") {
      // Auto-resume an in-flight recording from the last tab/session.
      const existing = this.loadActive();
      if (existing) {
        this.resumeFromPersisted(existing);
      }
    }
  }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    fn(this.status, null);
    return () => this.listeners.delete(fn);
  }

  private emit(session: RecordingSession | null = null): void {
    for (const fn of this.listeners) fn(this.status, session);
  }

  getStatus(): RecorderStatus {
    return this.status;
  }

  getEventCount(): number {
    return this.events.length;
  }

  getStartTime(): number {
    return this.startTime;
  }

  start(): void {
    if (typeof window === "undefined") return;
    if (this.status === "recording") return;

    this.events = [];
    this.sessionId = cryptoRandomId();
    this.startTime = Date.now();
    this.sequence = 0;
    this.status = "recording";
    this.lastPath = window.location.pathname;

    this.pushEvent("web.navigation", {
      tag: "location",
      selector: this.lastPath,
    }, { initial: true });

    this.attachListeners();
    this.startAutoSave();

    this.autoStopTimer = setTimeout(() => {
      this.stop();
    }, this.maxDurationMinutes * 60_000);

    this.persistActive();
    this.emit();
  }

  stop(): RecordingSession | null {
    if (this.status !== "recording") return null;

    // Final "page_exit" marker for clarity
    this.pushEvent(
      "web.page_exit",
      { tag: "session", selector: "stop" },
      { reason: "user_stopped" },
    );

    this.detachListeners();
    this.stopAutoSave();
    if (this.autoStopTimer) {
      clearTimeout(this.autoStopTimer);
      this.autoStopTimer = null;
    }
    this.clearPersistedActive();

    const endTime = Date.now();
    const durationSeconds = Math.max(1, Math.round((endTime - this.startTime) / 1000));
    const pages = Array.from(new Set(this.events.map((e) => e.page_path))).filter(Boolean);
    const session: RecordingSession = {
      session_id: this.sessionId,
      title: defaultSessionTitle(pages, durationSeconds),
      started_at: new Date(this.startTime).toISOString(),
      ended_at: new Date(endTime).toISOString(),
      duration_seconds: durationSeconds,
      events: this.events,
      event_count: this.events.length,
      pages_visited: pages,
      ingested: false,
    };
    this.status = "stopped";
    this.emit(session);
    return session;
  }

  reset(): void {
    this.events = [];
    this.status = "idle";
    this.sessionId = "";
    this.startTime = 0;
    this.sequence = 0;
    this.clearPersistedActive();
    this.emit();
  }

  /* ---------- persistence ---------- */

  private loadActive(): PersistedActive | null {
    try {
      const raw = window.localStorage.getItem(ACTIVE_SESSION_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as PersistedActive;
      if (!parsed?.session_id || !Array.isArray(parsed.events)) return null;
      return parsed;
    } catch {
      return null;
    }
  }

  private persistActive(): void {
    if (typeof window === "undefined") return;
    if (this.status !== "recording") return;
    const payload: PersistedActive = {
      session_id: this.sessionId,
      started_at_ms: this.startTime,
      sequence: this.sequence,
      events: this.events,
      last_path: this.lastPath,
    };
    try {
      window.localStorage.setItem(ACTIVE_SESSION_KEY, JSON.stringify(payload));
    } catch (err) {
      // Quota exceeded or similar — drop silently, memory buffer still works.
      console.warn("[mycelium-recorder] persistActive failed:", err);
    }
  }

  private clearPersistedActive(): void {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.removeItem(ACTIVE_SESSION_KEY);
    } catch {
      // ignore
    }
  }

  private resumeFromPersisted(p: PersistedActive): void {
    this.sessionId = p.session_id;
    this.startTime = p.started_at_ms;
    this.sequence = p.sequence;
    this.events = p.events.slice();
    this.lastPath = p.last_path || (typeof window !== "undefined" ? window.location.pathname : "");
    this.status = "recording";

    // Record the resume itself
    this.pushEvent(
      "web.page_resume",
      { tag: "session", selector: this.lastPath },
      { resumed_at: new Date().toISOString() },
    );

    this.attachListeners();
    this.startAutoSave();

    const elapsed = Date.now() - this.startTime;
    const remaining = this.maxDurationMinutes * 60_000 - elapsed;
    if (remaining > 0) {
      this.autoStopTimer = setTimeout(() => this.stop(), remaining);
    } else {
      // Already past cap — stop immediately
      this.stop();
      return;
    }

    this.emit();
  }

  private startAutoSave(): void {
    this.stopAutoSave();
    this.autoSaveTimer = setInterval(() => this.persistActive(), AUTOSAVE_INTERVAL_MS);
  }

  private stopAutoSave(): void {
    if (this.autoSaveTimer) {
      clearInterval(this.autoSaveTimer);
      this.autoSaveTimer = null;
    }
  }

  /* ---------- listeners ---------- */

  private attachListeners(): void {
    const onClick = (ev: MouseEvent) => this.handleClick(ev);
    const onSubmit = (ev: Event) => this.handleSubmit(ev);
    const onChange = (ev: Event) => this.handleChange(ev);
    const onVisibility = () => this.handleVisibility();
    const onPopstate = () => this.handleNavigation();
    const onPageHide = () => this.handlePageHide();
    const onBeforeUnload = () => this.handleBeforeUnload();

    document.addEventListener("click", onClick, true);
    document.addEventListener("submit", onSubmit, true);
    document.addEventListener("change", onChange, true);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("popstate", onPopstate);
    window.addEventListener("pagehide", onPageHide);
    window.addEventListener("beforeunload", onBeforeUnload);

    // Patch pushState / replaceState so we can observe client-side
    // navigation inside Next.js without pulling in framework-specific APIs.
    const origPush = history.pushState;
    const origReplace = history.replaceState;
    const patched = (fn: typeof history.pushState) => {
      return function (
        this: History,
        ...args: Parameters<typeof history.pushState>
      ) {
        const res = fn.apply(this, args);
        window.dispatchEvent(new Event("__mycelium_locationchange"));
        return res;
      };
    };
    history.pushState = patched(origPush);
    history.replaceState = patched(origReplace);
    const onLocChange = () => this.handleNavigation();
    window.addEventListener("__mycelium_locationchange", onLocChange);

    this.cleanupFns = [
      () => document.removeEventListener("click", onClick, true),
      () => document.removeEventListener("submit", onSubmit, true),
      () => document.removeEventListener("change", onChange, true),
      () => document.removeEventListener("visibilitychange", onVisibility),
      () => window.removeEventListener("popstate", onPopstate),
      () => window.removeEventListener("pagehide", onPageHide),
      () => window.removeEventListener("beforeunload", onBeforeUnload),
      () => window.removeEventListener("__mycelium_locationchange", onLocChange),
      () => {
        history.pushState = origPush;
        history.replaceState = origReplace;
      },
    ];
  }

  private detachListeners(): void {
    for (const fn of this.cleanupFns) fn();
    this.cleanupFns = [];
  }

  /* ---------- event capture ---------- */

  private pushEvent(
    type: WebSessionEventType,
    target: WebSessionEvent["target"],
    metadata?: Record<string, unknown>,
  ): void {
    if (this.events.length >= MAX_EVENTS) return;
    const ev: WebSessionEvent = {
      id: cryptoRandomId(),
      type,
      source: "web_recorder",
      timestamp: new Date().toISOString(),
      sequence: this.sequence++,
      page_path: typeof window !== "undefined" ? window.location.pathname : "",
      target,
      metadata,
    };
    this.events.push(ev);
    this.emit();
  }

  private handleClick(ev: MouseEvent): void {
    const el = ev.target as Element | null;
    if (!el || !isCaptureable(el)) return;
    const actionable = closestActionable(el);
    const target = describeElement(actionable ?? el);
    if (!target) return;
    this.pushEvent("web.click", target);
  }

  private handleSubmit(ev: Event): void {
    const form = ev.target as HTMLFormElement | null;
    if (!form || !isCaptureable(form)) return;
    const fields = Array.from(form.querySelectorAll("input, textarea, select"))
      .filter((f) => isCaptureable(f))
      .map((f) => {
        const el = f as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
        return {
          name: redactText(el.getAttribute("name") ?? ""),
          input_type: (el as HTMLInputElement).type ?? el.tagName.toLowerCase(),
        };
      });
    this.pushEvent(
      "web.form.submit",
      describeElement(form) ?? { tag: "form" },
      { field_count: fields.length, fields: fields.slice(0, 10) },
    );
  }

  private handleChange(ev: Event): void {
    const el = ev.target as Element | null;
    if (!el || !isCaptureable(el)) return;
    const t = (el as HTMLInputElement).type ?? "";
    if (!["checkbox", "radio"].includes(t) && el.tagName !== "SELECT") return;
    const target = describeElement(el);
    if (!target) return;
    this.pushEvent("web.input.change", target);
  }

  private handleVisibility(): void {
    const hidden = document.hidden;
    this.pushEvent(
      hidden ? "web.page_exit" : "web.page_resume",
      { tag: "document", selector: window.location.pathname },
      { hidden, reason: hidden ? "tab_hidden" : "tab_visible" },
    );
    // Flush immediately whenever focus leaves this tab.
    if (hidden) this.persistActive();
  }

  private handlePageHide(): void {
    this.pushEvent(
      "web.page_exit",
      { tag: "window", selector: window.location.pathname },
      { reason: "pagehide" },
    );
    this.persistActive();
  }

  private handleBeforeUnload(): void {
    this.pushEvent(
      "web.page_exit",
      { tag: "window", selector: window.location.pathname },
      { reason: "beforeunload" },
    );
    this.persistActive();
  }

  private handleNavigation(): void {
    const newPath = window.location.pathname;
    if (newPath === this.lastPath) return;
    this.lastPath = newPath;
    this.pushEvent("web.navigation", {
      tag: "location",
      selector: newPath,
    });
    this.persistActive();
  }
}

/* -------------------------------------------------------------------- */
/* Helpers                                                              */
/* -------------------------------------------------------------------- */

function cryptoRandomId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return (crypto as Crypto).randomUUID();
  }
  return `id_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

function isCaptureable(el: Element): boolean {
  if (el instanceof HTMLInputElement && el.type === "password") return false;
  let node: Element | null = el;
  while (node) {
    if (node.getAttribute?.("data-sensitive") === "true") return false;
    if (node.classList?.contains("sensitive")) return false;
    if (node.getAttribute?.("data-no-record") === "true") return false;
    node = node.parentElement;
  }
  return true;
}

function closestActionable(el: Element): Element | null {
  return (
    el.closest("button, a, [role='button'], [role='link'], [role='menuitem'], [role='tab']") ??
    null
  );
}

function describeElement(el: Element): WebSessionEvent["target"] | null {
  try {
    const tag = el.tagName.toLowerCase();
    const role = el.getAttribute("role") ?? undefined;
    const rawText = extractText(el);
    const text = redactText(rawText).slice(0, MAX_TEXT_LEN) || undefined;
    const selector = buildSelector(el);
    const href =
      el instanceof HTMLAnchorElement ? el.getAttribute("href") ?? undefined : undefined;
    const name =
      "name" in el && typeof (el as HTMLInputElement).name === "string"
        ? redactText((el as HTMLInputElement).name)
        : undefined;
    const input_type =
      el instanceof HTMLInputElement ? el.type : undefined;
    return { tag, role, text, selector, href, name, input_type };
  } catch {
    return null;
  }
}

function extractText(el: Element): string {
  const aria = el.getAttribute?.("aria-label");
  if (aria) return aria;
  if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
    return el.getAttribute("placeholder") ?? "";
  }
  const text = (el.textContent ?? "").replace(/\s+/g, " ").trim();
  return text;
}

function redactText(text: string): string {
  if (!text) return "";
  return text.replace(TOKEN_LIKE_RE, "[REDACTED]");
}

function buildSelector(el: Element): string {
  const parts: string[] = [];
  let node: Element | null = el;
  let depth = 0;
  while (node && depth < 4) {
    let segment = node.tagName.toLowerCase();
    const cls = Array.from(node.classList)
      .filter((c) => !c.startsWith("css-") && c.length < 24)
      .slice(0, 2);
    if (cls.length) segment += "." + cls.join(".");
    const testId = node.getAttribute?.("data-testid");
    if (testId) segment += `[data-testid="${testId}"]`;
    parts.unshift(segment);
    node = node.parentElement;
    depth++;
  }
  return parts.join(">");
}

function defaultSessionTitle(pages: string[], durationSeconds: number): string {
  const primary = pages[0] ?? "/";
  const mins = Math.max(1, Math.round(durationSeconds / 60));
  const date = new Date().toISOString().slice(0, 10);
  return `Session on ${primary} — ${mins}m (${date})`;
}

/* -------------------------------------------------------------------- */
/* Singleton accessor — one recorder per browser tab.                   */
/* -------------------------------------------------------------------- */

let _recorder: EventRecorder | null = null;

export function getEventRecorder(): EventRecorder {
  if (!_recorder) _recorder = new EventRecorder();
  return _recorder;
}
