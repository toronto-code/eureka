# Implementation Prompt: Web-Based Event Recording & Context Ingestion System

## Project Context: Mycelium/Eureka

**Mycelium** is an agentic company intelligence system built as a monorepo with:
- **Next.js 14 web app** (`apps/web`) - primary UI dashboard
- **FastAPI backend** (`apps/api`) - two surfaces: MVP `app.main:app` and Redis-centric `mycelium_api`
- **Event bus architecture** - Redis Streams with `events.raw` → `events.processed` pipeline
- **Multiple ingestion paths**: manual document upload, GitHub/Jira webhooks, sync service, and local git observer
- **Agent context system**: Agents use pre-fetched GitHub/Slack/Jira data (`_build_live_context`), project memory (`project_chunks`), and vector search (`project_data`)

Current ingestion UI (`/ingestion` page) is a simple uploader for documents and transcripts with title + content textarea. The system already has observer events tracking local git activity in Supabase (`observer_events` table).

---

## Goal: Web-Based User Event Recording System

### Vision
Create a **web-based recording feature** that:
1. **Captures user interaction events** in the web app (clicks, navigation, form submissions, page views, etc.)
2. **Compresses and structures** these events intelligently
3. **Stores them** as contextual artifacts for agent consumption
4. **Surfaces them** in the UI for users to review, title, and explicitly "ingest" as agent context
5. **Integrates seamlessly** with the existing event bus and ingestion architecture

This is NOT surveillance - it's opt-in, user-controlled recording of their own web app session for context capture.

---

## Architecture Design

### 1. Event Capture Layer (Frontend)

**Location**: `apps/web/lib/event-recorder.ts` (new file)

**Design**:
- Client-side TypeScript class `EventRecorder` that:
  - Listens to browser events: `click`, `navigation`, `form submit`, `input change` (debounced), `page visibility`
  - Captures sanitized event data: timestamp, event type, target element (sanitized selector), page path, user action description
  - NEVER captures sensitive data: passwords, API keys, form field values (only field names/types)
  - Uses a circular buffer to keep last N events in memory (e.g., 500 events max)
  - Provides methods: `startRecording()`, `stopRecording()`, `getEvents()`, `clear()`, `compress()`

**Event Schema** (extends `MyceliumEvent` format):
```typescript
interface WebSessionEvent {
  id: string;                          // uuid
  type: string;                        // "web.click", "web.navigation", "web.form.submit", etc.
  source: "web_recorder";
  actor: MyceliumEventActor;           // user_id from auth
  object: {
    id: string;                        // element selector or page path
    type: string;                      // "button" | "link" | "page" | "form"
    url?: string;
  };
  timestamp: string;                   // ISO 8601
  schema_version: "1.0";
  metadata: {
    page_path: string;
    element_text?: string;             // button/link text (sanitized)
    element_selector?: string;         // simplified CSS selector
    element_role?: string;             // ARIA role
    session_id: string;                // recording session ID
    sequence_number: number;           // order in session
  };
  correlation_id: string;              // session:<session_id>
  parent_correlation_id?: string;
}
```

**Compression Strategy**:
- Deduplicate sequential identical events (e.g., multiple clicks on same button)
- Aggregate navigation sequences into "journeys"
- Summarize repetitive patterns (e.g., "Clicked through 5 task items")
- Detect and label common workflows (e.g., "Created new task workflow", "Reviewed ingestion documents")
- Reduce verbosity: store only meaningful state transitions

**Privacy-First Design**:
- Explicitly exclude input field VALUES (only capture field names/types)
- Redact any text that matches patterns for secrets (API keys, tokens, emails with special markers)
- Never send data automatically - all ingestion is manual user action
- Show raw events to user before ingestion for review

---

### 2. Recording UI Component

**Location**: `apps/web/components/EventRecorder.tsx` (new file)

**Design**:
- Floating "Record" button in the app (top-right corner, near user profile)
- States: 
  - **Idle** (gray circle button with "Record" icon)
  - **Recording** (red pulsing circle with timer, "Stop" button)
  - **Recorded** (green checkmark, shows event count, "Review & Ingest" button)
- When recording stops, shows modal with:
  - Event count and duration
  - Timeline visualization of events (grouped by page/workflow)
  - Preview of compressed events
  - Title input field (e.g., "Task creation workflow on 2026-05-02")
  - Description textarea (optional)
  - Privacy notice with checkbox: "I confirm this recording contains no sensitive data"
  - "Ingest as Context" primary button
  - "Discard" secondary button
  - "Download JSON" tertiary button (for manual inspection)

**UI Location in Layout**:
- Add `<EventRecorder />` component to `apps/web/app/layout.tsx` inside `AppShell`
- Position fixed in top-right, z-index above all content
- Responsive: collapses to icon-only on mobile

**Visual Design**:
- Follows existing Mycelium design system from `globals.css`
- Recording indicator: small red dot in top-right corner with subtle glow animation
- Modal: uses `.card` class with custom styling for timeline
- Timeline: vertical list with timestamps, grouped by page, uses existing color tokens

---

### 3. Enhanced Ingestion Page UI

**Location**: `apps/web/app/ingestion/page.tsx` (modify existing)

**Changes**:
- Add new tab/section: "Session Recordings"
- Show list of all recorded sessions (stored locally in browser until ingested):
  - Session title (user-provided or auto-generated)
  - Date/time
  - Event count
  - Duration
  - Status: "Draft" | "Ingested"
- Each session row has:
  - "Review" button → opens modal from EventRecorder component
  - "Ingest" button → triggers ingestion
  - "Delete" button → removes from localStorage
- Add tab for "Ingested Sessions" showing sessions that have been sent to backend
- Enhance "Add document or transcript" card with new option:
  - Source type dropdown adds "Web Session Recording"

**Modified Upload Component**:
- `IngestionUploader.tsx` should accept new source type: `"web_session"`
- When source type is "web_session", show "Select Recording" dropdown instead of textarea
- Recording dropdown populated from `EventRecorder` stored sessions
- On submit, compress events and send as structured JSON

---

### 4. Backend Ingestion Extension

**Location**: `apps/api/app/routes/ingestion.py` (modify)

**Changes**:
- Extend `POST /ingestion/upload` to accept `source_type="web_session"`
- When web_session detected:
  - Parse `raw_text` as JSON array of `WebSessionEvent`
  - Validate event schema
  - Run compression/summarization:
    - Extract workflow patterns
    - Identify key user journeys
    - Create high-level summary
  - Store in `source_documents` with:
    - `source_type = "web_session"`
    - `title` = user-provided title
    - `content` = compressed markdown summary + full JSON in metadata
  - Chunk appropriately for vector search:
    - High-level summary as one chunk
    - Each workflow/journey as separate chunks
    - Store full event JSON in metadata for retrieval

**New Service**: `apps/api/app/ingestion/session_processor.py`
```python
class SessionProcessor:
    """Process web session events into agent-friendly context."""
    
    def compress_events(self, events: list[dict]) -> str:
        """Convert raw events into markdown summary."""
        # Group by page
        # Identify workflows (e.g., navigation patterns)
        # Generate human-readable narrative
        # Return markdown with sections:
        #   - Session Overview (duration, pages visited)
        #   - Key Actions (high-impact interactions)
        #   - Workflows Observed (detected patterns)
        #   - Detailed Timeline (compressed event list)
        
    def detect_workflows(self, events: list[dict]) -> list[dict]:
        """Identify common workflow patterns."""
        # Pattern matching for:
        #   - Task creation (navigated to /tasks, clicked new, filled form)
        #   - Document ingestion (navigated to /ingestion, uploaded file)
        #   - Agent execution (clicked run, waited for result, reviewed output)
        #   - Settings configuration (navigated to /settings, modified fields)
        
    def extract_insights(self, events: list[dict]) -> dict:
        """Extract metadata about user behavior."""
        # Return:
        #   - most_visited_pages
        #   - common_actions
        #   - time_spent_per_page
        #   - interaction_frequency
        #   - identified_workflows
```

---

### 5. Agent Context Integration

**Location**: `apps/api/app/routes/agent_chat.py` (modify `_build_live_context`)

**Changes**:
- Add new section to context: "Recent User Web Sessions"
- Query `source_documents` where `source_type = "web_session"` and `created_at` within last 7 days
- For each session:
  - Include compressed summary
  - Include detected workflows
  - Include insights metadata
- Format as markdown section:

```markdown
## Recent User Web Sessions

The user has recorded the following web app sessions for context:

### Session: Task creation workflow on 2026-05-02 (2 minutes, 47 events)

**Key Actions:**
- Navigated to Tasks page
- Clicked "New Task" button
- Filled task form (title, description, assignee)
- Submitted task
- Reviewed task detail page
- Clicked "Run Agent" for new task

**Workflows Detected:**
- Task Creation: Standard task creation flow with all required fields
- Agent Execution: Immediately requested agent assistance after creation

**Insights:**
- User is comfortable with task creation interface
- User expects agent to assist with new tasks immediately
- User reviewed agent output before closing

...
```

**Location**: `apps/api/app/agents/ol/classifier.py` (modify `_shallow_retrieve`)

**Changes**:
- Include web session chunks in retrieval query
- When user query relates to "how I use the system" or "what I was doing", prioritize web session chunks
- Add recency bias for web sessions (recent sessions more relevant)

---

### 6. Event Bus Integration (Optional - for real-time streaming)

**Location**: `apps/web/lib/event-recorder.ts` (extend)

**Design**:
- Add optional real-time streaming mode:
  - If user enables "Live Streaming" toggle, events are published to backend as they occur
  - Events go to `POST /integrations/ingest` (mycelium_api endpoint)
  - Published to `events.raw` topic with `source="web_recorder"`
  - Classification service processes for PII
  - Stored in `events` table and `observer_events` table (dual storage)
  - Knowledge service can build graph nodes for user interaction patterns

**Backend Route**: `apps/api/src/mycelium_api/routers/integrations.py` (already exists)
- Already has `POST /integrations/ingest` that publishes to Redis event bus
- Extend to accept `source="web_recorder"` events
- Validate `WebSessionEvent` schema
- Publish to `events.raw` with correlation_id = `session:<session_id>`

**Note**: Live streaming is OPTIONAL Phase 2 - initial implementation should focus on manual recording + ingestion flow.

---

## Database Schema Changes

### 1. Extend `source_documents` table
**File**: `apps/api/app/models/documents.py`

No schema changes needed - existing `source_type` column can accept `"web_session"` value.

Add to code:
```python
class SourceType(str, Enum):
    DOC = "doc"
    TRANSCRIPT = "transcript"
    WEB_SESSION = "web_session"  # NEW
```

### 2. New table: `web_sessions` (Optional - for richer metadata)
**File**: `apps/api/app/models/web_sessions.py` (new)

```python
class WebSession(Base):
    __tablename__ = "web_sessions"
    
    id = Column(String, primary_key=True)  # uuid
    user_id = Column(String, nullable=False, index=True)
    session_id = Column(String, nullable=False, unique=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=False)
    duration_seconds = Column(Integer, nullable=False)
    
    event_count = Column(Integer, nullable=False)
    compressed_summary = Column(Text, nullable=False)  # markdown
    detected_workflows = Column(JSON, nullable=False)  # list of workflow dicts
    insights = Column(JSON, nullable=False)  # metadata dict
    
    # Link to ingested document
    document_id = Column(String, ForeignKey("source_documents.id"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    ingested_at = Column(DateTime(timezone=True), nullable=True)
    
    # Full event JSON for replay/debugging (optional, could be S3 path)
    raw_events = Column(JSON, nullable=True)
```

### 3. Extend Supabase schema (for web sessions)
**File**: `supabase/schema.sql` (modify)

Add after `observer_events` table:

```sql
-- Web session recordings (user-captured browser interaction sessions)
create table if not exists public.web_sessions (
  id          text primary key,
  user_id     uuid references auth.users(id) on delete cascade,
  session_id  text unique not null,
  title       text not null,
  description text,
  started_at  timestamptz not null,
  ended_at    timestamptz not null,
  duration_seconds integer not null,
  event_count integer not null,
  compressed_summary text not null,
  detected_workflows jsonb not null default '[]'::jsonb,
  insights    jsonb not null default '{}'::jsonb,
  document_id text,  -- link to source_documents
  created_at  timestamptz default now(),
  ingested_at timestamptz
);

create index if not exists web_sessions_user_idx on public.web_sessions (user_id, created_at desc);
create index if not exists web_sessions_session_idx on public.web_sessions (session_id);
create index if not exists web_sessions_ingested_idx on public.web_sessions (ingested_at) where ingested_at is not null;

-- RLS policies
alter table public.web_sessions enable row level security;

drop policy if exists "web_sessions own select" on public.web_sessions;
create policy "web_sessions own select" on public.web_sessions
  for select using (auth.uid() = user_id);

drop policy if exists "web_sessions own insert" on public.web_sessions;
create policy "web_sessions own insert" on public.web_sessions
  for insert with check (auth.uid() = user_id);

drop policy if exists "web_sessions own update" on public.web_sessions;
create policy "web_sessions own update" on public.web_sessions
  for update using (auth.uid() = user_id);

drop policy if exists "web_sessions own delete" on public.web_sessions;
create policy "web_sessions own delete" on public.web_sessions
  for delete using (auth.uid() = user_id);
```

---

## Implementation Steps (Detailed)

### Phase 1: Core Recording Infrastructure (Frontend)

1. **Create Event Recorder Library** (`apps/web/lib/event-recorder.ts`):
   ```typescript
   export class EventRecorder {
     private events: WebSessionEvent[] = [];
     private sessionId: string;
     private isRecording: boolean = false;
     private startTime: number;
     private sequenceNumber: number = 0;
     
     constructor(private maxEvents: number = 500) {}
     
     startRecording(userId: string): void {
       // Initialize session, attach event listeners
     }
     
     stopRecording(): RecordingSession {
       // Detach listeners, return session with events
     }
     
     private handleClick(event: MouseEvent): void {
       // Capture click event with sanitization
     }
     
     private handleNavigation(event: Event): void {
       // Capture navigation/route change
     }
     
     private handleFormSubmit(event: Event): void {
       // Capture form submission (NO VALUES)
     }
     
     compress(): CompressedSession {
       // Run compression algorithms
     }
     
     // Privacy methods
     private sanitizeSelector(element: Element): string {
       // Generate safe CSS selector without IDs/sensitive attrs
     }
     
     private shouldCapture(event: Event): boolean {
       // Filter out events from password fields, etc.
     }
   }
   
   export interface RecordingSession {
     sessionId: string;
     userId: string;
     startTime: number;
     endTime: number;
     events: WebSessionEvent[];
     eventCount: number;
     durationSeconds: number;
   }
   
   export interface CompressedSession extends RecordingSession {
     summary: string;
     workflows: Workflow[];
     insights: SessionInsights;
   }
   ```

2. **Create Context/Hook for App-Wide Access** (`apps/web/lib/event-recorder-context.tsx`):
   ```typescript
   export const EventRecorderContext = createContext<EventRecorder | null>(null);
   
   export function EventRecorderProvider({ children }: { children: ReactNode }) {
     const recorder = useMemo(() => new EventRecorder(), []);
     return (
       <EventRecorderContext.Provider value={recorder}>
         {children}
       </EventRecorderContext.Provider>
     );
   }
   
   export function useEventRecorder() {
     const recorder = useContext(EventRecorderContext);
     if (!recorder) throw new Error("EventRecorder not found");
     return recorder;
   }
   ```

3. **Wrap App Layout** (`apps/web/app/layout.tsx`):
   ```typescript
   import { EventRecorderProvider } from '@/lib/event-recorder-context';
   
   export default function RootLayout({ children }) {
     return (
       <html>
         <body>
           <AuthProvider>
             <EventRecorderProvider>
               <AppShell>
                 {children}
               </AppShell>
             </EventRecorderProvider>
           </AuthProvider>
         </body>
       </html>
     );
   }
   ```

4. **Add Browser Event Listeners**:
   - Listen to `click` on document
   - Listen to Next.js router events for navigation
   - Listen to `submit` on forms
   - Listen to `visibilitychange` for session pauses
   - Debounce input events (capture only final value after 2s idle)

### Phase 2: Recording UI Component

1. **Create EventRecorder Component** (`apps/web/components/EventRecorder.tsx`):
   ```typescript
   "use client";
   
   export function EventRecorder() {
     const recorder = useEventRecorder();
     const [status, setStatus] = useState<'idle' | 'recording' | 'recorded'>('idle');
     const [session, setSession] = useState<RecordingSession | null>(null);
     const [showModal, setShowModal] = useState(false);
     
     const startRecording = () => {
       recorder.startRecording(userId);
       setStatus('recording');
     };
     
     const stopRecording = () => {
       const session = recorder.stopRecording();
       setSession(session);
       setStatus('recorded');
       setShowModal(true);
     };
     
     return (
       <>
         <RecordButton status={status} onStart={startRecording} onStop={stopRecording} />
         {showModal && session && (
           <SessionReviewModal
             session={session}
             onIngest={handleIngest}
             onDiscard={handleDiscard}
             onClose={() => setShowModal(false)}
           />
         )}
       </>
     );
   }
   ```

2. **Create SessionReviewModal** component with:
   - Timeline visualization (use existing design tokens)
   - Event grouping by page
   - Workflow detection visualization
   - Title/description inputs
   - Privacy confirmation checkbox
   - Action buttons (Ingest, Discard, Download)

3. **Add to Layout**:
   - Import in `apps/web/app/layout.tsx`
   - Render conditionally (only when authenticated)
   - Position fixed with high z-index

### Phase 3: Enhanced Ingestion Page

1. **Modify Ingestion Page** (`apps/web/app/ingestion/page.tsx`):
   - Add tabs: "Upload" | "Recordings" | "Documents"
   - Load recordings from localStorage + Supabase
   - Show recording list with metadata
   - Add review/ingest/delete actions per recording

2. **Modify IngestionUploader** (`apps/web/components/IngestionUploader.tsx`):
   - Add "web_session" to source type dropdown
   - When web_session selected, show recording selector instead of textarea
   - Load available recordings from localStorage
   - On submit, serialize recording as JSON string

3. **Create RecordingsManager** component:
   ```typescript
   export function RecordingsManager() {
     const [recordings, setRecordings] = useState<RecordingSession[]>([]);
     
     useEffect(() => {
       // Load from localStorage
       const stored = loadRecordingsFromLocalStorage();
       setRecordings(stored);
     }, []);
     
     return (
       <div className="card">
         <h3>Session Recordings</h3>
         <div className="list-card">
           {recordings.map(recording => (
             <RecordingRow
               key={recording.sessionId}
               recording={recording}
               onReview={handleReview}
               onIngest={handleIngest}
               onDelete={handleDelete}
             />
           ))}
         </div>
       </div>
     );
   }
   ```

### Phase 4: Backend Processing

1. **Create Session Processor** (`apps/api/app/ingestion/session_processor.py`):
   ```python
   class SessionProcessor:
       def __init__(self):
           self.workflow_patterns = self._load_workflow_patterns()
       
       def process_session(
           self,
           events: list[dict],
           title: str,
           description: str | None = None
       ) -> ProcessedSession:
           """Process raw session events into agent-friendly context."""
           
           # Group events by page
           pages = self._group_by_page(events)
           
           # Detect workflows
           workflows = self.detect_workflows(events)
           
           # Extract insights
           insights = self.extract_insights(events)
           
           # Generate compressed summary
           summary = self._generate_summary(pages, workflows, insights)
           
           return ProcessedSession(
               title=title,
               description=description,
               summary=summary,
               workflows=workflows,
               insights=insights,
               event_count=len(events),
               duration_seconds=self._calculate_duration(events)
           )
       
       def _generate_summary(
           self,
           pages: dict,
           workflows: list[Workflow],
           insights: dict
       ) -> str:
           """Generate markdown summary of session."""
           parts = [
               f"# {self.title}",
               "",
               "## Session Overview",
               f"- Duration: {insights['duration']} seconds",
               f"- Pages Visited: {len(pages)}",
               f"- Total Actions: {insights['action_count']}",
               "",
               "## Key Actions",
           ]
           
           # Add top 10 most significant actions
           for action in insights['key_actions']:
               parts.append(f"- {action['timestamp']}: {action['description']}")
           
           parts.append("")
           parts.append("## Detected Workflows")
           
           for workflow in workflows:
               parts.append(f"### {workflow['name']}")
               parts.append(f"- Steps: {len(workflow['steps'])}")
               parts.append(f"- Duration: {workflow['duration']}s")
               for step in workflow['steps']:
                   parts.append(f"  - {step['description']}")
           
           parts.append("")
           parts.append("## Page Journey")
           
           for page_path, page_events in pages.items():
               parts.append(f"### {page_path}")
               parts.append(f"- Time Spent: {page_events['duration']}s")
               parts.append(f"- Actions: {len(page_events['events'])}")
           
           return "\n".join(parts)
       
       def detect_workflows(self, events: list[dict]) -> list[Workflow]:
           """Detect common workflow patterns using heuristics."""
           workflows = []
           
           # Pattern: Task Creation
           task_creation = self._detect_task_creation(events)
           if task_creation:
               workflows.append(task_creation)
           
           # Pattern: Document Ingestion
           doc_ingestion = self._detect_doc_ingestion(events)
           if doc_ingestion:
               workflows.append(doc_ingestion)
           
           # Pattern: Agent Execution
           agent_exec = self._detect_agent_execution(events)
           if agent_exec:
               workflows.append(agent_exec)
           
           return workflows
       
       def _detect_task_creation(self, events: list[dict]) -> Workflow | None:
           """Detect task creation workflow."""
           # Look for: navigate to /tasks -> click new -> form interactions -> submit
           # Return Workflow object if pattern found
           pass
       
       def extract_insights(self, events: list[dict]) -> dict:
           """Extract behavioral insights."""
           return {
               "duration": self._calculate_duration(events),
               "action_count": len(events),
               "most_visited_pages": self._count_pages(events),
               "common_actions": self._count_actions(events),
               "time_distribution": self._time_per_page(events),
               "interaction_patterns": self._analyze_patterns(events),
               "key_actions": self._identify_key_actions(events)
           }
   ```

2. **Extend Ingestion Route** (`apps/api/app/routes/ingestion.py`):
   ```python
   from app.ingestion.session_processor import SessionProcessor
   
   @router.post("/upload")
   async def upload_document(
       title: str = Form(...),
       source_type: str = Form(...),
       raw_text: str = Form(None),
       raw_json: str = Form(None),  # NEW: for web sessions
       session: Session = Depends(get_session)
   ):
       if source_type == "web_session":
           # Parse JSON events
           events = json.loads(raw_json)
           
           # Process with SessionProcessor
           processor = SessionProcessor()
           processed = processor.process_session(
               events=events,
               title=title,
               description=None
           )
           
           # Store as document with compressed summary
           doc_id = ingestion_service.ingest_document(
               session=session,
               source_type="web_session",
               title=title,
               content=processed.summary,
               metadata={
                   "session_id": events[0]["metadata"]["session_id"],
                   "event_count": processed.event_count,
                   "duration_seconds": processed.duration_seconds,
                   "workflows": [w.dict() for w in processed.workflows],
                   "insights": processed.insights,
                   "raw_events": events  # Store full events in metadata
               }
           )
           
           return {"document_id": doc_id, "chunks": len(processed.summary)}
       
       else:
           # Existing document/transcript logic
           ...
   ```

3. **Update Agent Context** (`apps/api/app/routes/agent_chat.py`):
   ```python
   async def _build_live_context() -> str:
       # ... existing GitHub/Slack/Jira context ...
       
       # Add web sessions
       web_sessions_context = await _fetch_web_sessions_context()
       
       return f"""
       {existing_context}
       
       {web_sessions_context}
       """
   
   async def _fetch_web_sessions_context() -> str:
       """Fetch recent web session recordings for context."""
       with get_session() as session:
           recent_sessions = session.query(SourceDocument).filter(
               SourceDocument.source_type == "web_session",
               SourceDocument.created_at >= datetime.now() - timedelta(days=7)
           ).order_by(SourceDocument.created_at.desc()).limit(5).all()
           
           if not recent_sessions:
               return ""
           
           parts = ["## Recent User Web Sessions", ""]
           
           for doc in recent_sessions:
               metadata = doc.metadata
               parts.append(f"### {doc.title}")
               parts.append(f"- Duration: {metadata['duration_seconds']}s")
               parts.append(f"- Events: {metadata['event_count']}")
               parts.append("")
               
               # Add workflows
               if metadata.get('workflows'):
                   parts.append("**Detected Workflows:**")
                   for workflow in metadata['workflows']:
                       parts.append(f"- {workflow['name']}: {workflow['description']}")
                   parts.append("")
               
               # Add compressed summary (first 500 chars)
               parts.append(doc.content[:500] + "...")
               parts.append("")
           
           return "\n".join(parts)
   ```

### Phase 5: Storage & Persistence

1. **LocalStorage Management** (`apps/web/lib/storage.ts`):
   ```typescript
   const RECORDINGS_KEY = 'mycelium_recordings';
   
   export function saveRecording(session: RecordingSession): void {
     const recordings = getRecordings();
     recordings.push(session);
     localStorage.setItem(RECORDINGS_KEY, JSON.stringify(recordings));
   }
   
   export function getRecordings(): RecordingSession[] {
     const stored = localStorage.getItem(RECORDINGS_KEY);
     return stored ? JSON.parse(stored) : [];
   }
   
   export function deleteRecording(sessionId: string): void {
     const recordings = getRecordings().filter(r => r.sessionId !== sessionId);
     localStorage.setItem(RECORDINGS_KEY, JSON.stringify(recordings));
   }
   
   export function markIngested(sessionId: string): void {
     const recordings = getRecordings();
     const recording = recordings.find(r => r.sessionId === sessionId);
     if (recording) {
       (recording as any).ingested = true;
       localStorage.setItem(RECORDINGS_KEY, JSON.stringify(recordings));
     }
   }
   ```

2. **Supabase Storage** (Optional - for cloud sync):
   - Create API route: `apps/web/app/api/recordings/route.ts`
   - GET: Load user's recordings from Supabase `web_sessions` table
   - POST: Save recording to Supabase for backup/sync
   - DELETE: Remove recording from Supabase

3. **Migration Strategy**:
   - Start with localStorage only for MVP
   - Phase 2: Add Supabase sync for cross-device access
   - Show "Local only" badge for recordings not synced

### Phase 6: Privacy & Security

1. **Input Sanitization** in `EventRecorder`:
   ```typescript
   private shouldCapture(element: Element): boolean {
     // Never capture password fields
     if (element instanceof HTMLInputElement && element.type === 'password') {
       return false;
     }
     
     // Never capture elements with data-sensitive attribute
     if (element.hasAttribute('data-sensitive')) {
       return false;
     }
     
     // Never capture from .sensitive class
     if (element.classList.contains('sensitive')) {
       return false;
     }
     
     return true;
   }
   
   private sanitizeText(text: string): string {
     // Redact anything that looks like an API key
     text = text.replace(/\b[a-zA-Z0-9]{32,}\b/g, '[REDACTED_KEY]');
     
     // Redact email addresses (optional, could be too aggressive)
     // text = text.replace(/[\w.-]+@[\w.-]+\.\w+/g, '[EMAIL]');
     
     return text;
   }
   ```

2. **User Controls**:
   - Add settings page toggle: "Enable Session Recording"
   - Add per-page opt-out: data attribute on sensitive pages
   - Clear consent modal on first recording
   - Export/delete all recordings option in settings

3. **Backend Validation**:
   - Validate all events have proper schema
   - Reject events with suspicious patterns (e.g., too many in short time)
   - Rate limit ingestion endpoint per user

### Phase 7: Visualization & Analytics

1. **Session Timeline Component** (`apps/web/components/SessionTimeline.tsx`):
   ```typescript
   export function SessionTimeline({ events }: { events: WebSessionEvent[] }) {
     const grouped = groupByPage(events);
     
     return (
       <div className="timeline">
         {Object.entries(grouped).map(([page, pageEvents]) => (
           <div key={page} className="timeline-page">
             <div className="timeline-page-header">
               <h4>{page}</h4>
               <span className="badge">{pageEvents.length} events</span>
             </div>
             <div className="timeline-events">
               {pageEvents.map(event => (
                 <TimelineEvent key={event.id} event={event} />
               ))}
             </div>
           </div>
         ))}
       </div>
     );
   }
   
   function TimelineEvent({ event }: { event: WebSessionEvent }) {
     return (
       <div className="timeline-event">
         <span className="timeline-time">
           {formatTime(event.timestamp)}
         </span>
         <span className="timeline-action">
           {event.type.replace('web.', '')}
         </span>
         <span className="timeline-target">
           {event.metadata.element_text || event.object.id}
         </span>
       </div>
     );
   }
   ```

2. **Workflow Visualization**:
   - Show detected workflows as flowchart
   - Use Mermaid.js or simple SVG
   - Highlight key decision points

3. **Insights Dashboard** (in ingestion page):
   - Most used pages
   - Common workflows
   - Average session duration
   - Most frequent actions

### Phase 8: Testing & Validation

1. **Frontend Tests**:
   - EventRecorder unit tests (mocking DOM events)
   - Component integration tests (recording flow)
   - Privacy validation tests (ensure no sensitive data captured)

2. **Backend Tests**:
   - SessionProcessor unit tests (workflow detection)
   - Compression accuracy tests
   - Ingestion endpoint tests

3. **E2E Tests**:
   - Full recording -> review -> ingest -> agent use flow
   - Privacy: ensure password fields never captured
   - Storage: verify localStorage persistence

---

## UI/UX Mockup Descriptions

### 1. Recording Button (Idle State)
- **Location**: Top-right corner, left of user profile
- **Appearance**: Small circular button (32px diameter)
- **Icon**: Gray circle outline with red dot inside
- **Hover**: Shows tooltip "Start Recording Session"
- **Color**: `var(--neutral-500)`

### 2. Recording Button (Recording State)
- **Appearance**: Red pulsing circle
- **Animation**: Gentle pulse (scale 1.0 -> 1.1 -> 1.0, 2s loop)
- **Icon**: Red filled circle with timer text overlay
- **Color**: `var(--red)`
- **Additional**: Duration counter (e.g., "1:23")
- **Hover**: Shows tooltip "Stop Recording (X events captured)"

### 3. Recording Button (Recorded State)
- **Appearance**: Green checkmark circle
- **Icon**: Checkmark in circle
- **Color**: `var(--green)`
- **Badge**: Event count badge on top-right (e.g., "47")
- **Hover**: Shows tooltip "Review & Ingest Recording"

### 4. Session Review Modal
- **Size**: Large modal (800px wide, 80vh tall)
- **Header**: 
  - Title: "Session Recording Ready"
  - Close button (X)
  - Download JSON button (icon)
- **Body** (scrollable):
  - **Summary Section**:
    - Duration: "2 minutes 34 seconds"
    - Event Count: "47 events"
    - Pages Visited: "5 pages"
  - **Timeline Section**:
    - Vertical timeline with page groupings
    - Each event shows: time, icon (based on type), description
    - Click event to expand details
  - **Workflows Section** (if detected):
    - List of detected workflows with step counts
    - Expandable to show steps
  - **Ingestion Form**:
    - Title input (required)
    - Description textarea (optional)
    - Privacy checkbox: "I confirm no sensitive data is included"
- **Footer**:
  - "Discard" button (secondary, left)
  - "Ingest as Context" button (primary, right, disabled until checkbox)

### 5. Ingestion Page - Recordings Tab
- **Layout**: Grid of recording cards
- **Card Contents**:
  - Icon: Web session icon (browser window)
  - Title: User-provided or auto-generated
  - Metadata: Date, duration, event count
  - Status badge: "Draft" (gray) or "Ingested" (green)
  - Actions:
    - "Review" icon button
    - "Ingest" icon button (if not ingested)
    - "Delete" icon button
- **Empty State**: "No recordings yet. Click the Record button in the top-right to capture a session."

### 6. Enhanced Upload Form
- **Source Type Dropdown**:
  - "Document / spec / README"
  - "Working-session transcript"
  - "Web Session Recording" ← NEW
- **Conditional UI**:
  - When "Web Session Recording" selected:
    - Hide textarea
    - Show "Select Recording" dropdown (populated from localStorage)
    - Show preview of selected recording (event count, duration)
  - When other types selected:
    - Show existing textarea

---

## Configuration & Environment Variables

Add to `.env`:

```env
# Event Recording Feature Flags
ENABLE_WEB_SESSION_RECORDING=true          # Master toggle
WEB_SESSION_MAX_EVENTS=500                 # Max events per session
WEB_SESSION_MAX_DURATION_MINUTES=30        # Auto-stop after X minutes
WEB_SESSION_STORAGE_DAYS=30                # Delete recordings older than X days

# Privacy Settings
WEB_SESSION_REDACT_PATTERNS="api[_-]?key|token|secret|password"
WEB_SESSION_EXCLUDE_PAGES="/settings/api-keys,/admin"

# Event Bus Integration (Phase 2)
WEB_SESSION_ENABLE_STREAMING=false         # Enable real-time event streaming
```

Add to `apps/web/lib/config.ts`:

```typescript
export const EVENT_RECORDER_CONFIG = {
  enabled: process.env.NEXT_PUBLIC_ENABLE_WEB_SESSION_RECORDING === 'true',
  maxEvents: parseInt(process.env.NEXT_PUBLIC_WEB_SESSION_MAX_EVENTS || '500'),
  maxDurationMinutes: parseInt(process.env.NEXT_PUBLIC_WEB_SESSION_MAX_DURATION_MINUTES || '30'),
  excludePages: (process.env.NEXT_PUBLIC_WEB_SESSION_EXCLUDE_PAGES || '').split(','),
};
```

---

## Success Metrics

### User Adoption
- % of users who enable recording
- Average recordings per user per week
- % of recordings ingested (vs discarded)

### Context Quality
- Agent responses citing web session context
- User feedback on context relevance
- Reduced clarification questions from agents

### Technical Health
- Average event count per session
- Compression ratio (raw events : compressed summary)
- Storage usage per user
- Ingestion processing time

---

## Future Enhancements (Out of Scope for MVP)

1. **AI-Powered Summarization**:
   - Use LLM to generate natural language summaries
   - "You created 3 tasks, reviewed 2 PRs, and configured GitHub integration"

2. **Pattern Learning**:
   - Learn user-specific workflow patterns over time
   - Suggest shortcuts based on common patterns
   - Detect anomalies (unusual behavior)

3. **Collaborative Sessions**:
   - Share sessions with team members
   - "Show me how you did X" feature
   - Team workflow libraries

4. **Real-Time Assistance**:
   - Agent watches live session and offers help
   - "It looks like you're trying to create a task. Would you like me to..."
   - Proactive suggestions based on current action

5. **Session Replay**:
   - Visual replay of recorded session
   - Step-through debugger for workflows
   - Export as video/GIF

6. **Cross-Device Sync**:
   - Sync recordings across devices
   - Resume sessions on different machines

7. **Workflow Templates**:
   - Save common workflows as templates
   - One-click replay of template workflow
   - Share templates with team

8. **Integration with Observer**:
   - Correlate web sessions with local git activity
   - Show unified timeline (web + git)
   - Richer context for agents

---

## Key Principles for Implementation

1. **Privacy First**: User controls everything, nothing automatic, explicit consent required
2. **Progressive Enhancement**: Works without backend changes (localStorage only), better with backend
3. **Non-Invasive**: Recording UI stays out of the way, doesn't disrupt workflow
4. **Useful Context**: Compressed summaries must be genuinely helpful to agents
5. **Existing Patterns**: Follow Mycelium's design system and architecture patterns
6. **Opt-In Everywhere**: Every feature is opt-in, never forced
7. **Data Minimization**: Capture only what's needed, redact aggressively

---

## Files to Create (New)

### Frontend
- `apps/web/lib/event-recorder.ts` - Core recording logic
- `apps/web/lib/event-recorder-context.tsx` - React context/hooks
- `apps/web/lib/storage.ts` - LocalStorage management
- `apps/web/lib/compression.ts` - Client-side compression algorithms
- `apps/web/components/EventRecorder.tsx` - Recording button & controls
- `apps/web/components/SessionReviewModal.tsx` - Review modal UI
- `apps/web/components/SessionTimeline.tsx` - Timeline visualization
- `apps/web/components/RecordingsManager.tsx` - Recording list management
- `apps/web/components/RecordingCard.tsx` - Individual recording card
- `apps/web/app/api/recordings/route.ts` - API routes for recordings

### Backend
- `apps/api/app/ingestion/session_processor.py` - Session processing logic
- `apps/api/app/models/web_sessions.py` - Database model
- `apps/api/app/schemas/web_session.py` - Pydantic schemas

### Database
- Migration file for `web_sessions` table (SQLAlchemy + Supabase)

### Types
- `packages/shared-types/typescript/src/web_session.ts` - TS types
- `packages/shared-types/python/src/mycelium_shared_types/web_session.py` - Python types

---

## Files to Modify (Existing)

### Frontend
- `apps/web/app/layout.tsx` - Add EventRecorderProvider & EventRecorder component
- `apps/web/app/ingestion/page.tsx` - Add Recordings tab/section
- `apps/web/components/IngestionUploader.tsx` - Add web_session source type
- `apps/web/app/globals.css` - Add recording UI styles

### Backend
- `apps/api/app/routes/ingestion.py` - Extend upload endpoint
- `apps/api/app/routes/agent_chat.py` - Add web session context to `_build_live_context`
- `apps/api/app/agents/ol/classifier.py` - Include web sessions in retrieval
- `apps/api/app/models/documents.py` - Add web_session to SourceType enum
- `apps/api/app/ingestion/service.py` - Handle web_session type

### Database
- `supabase/schema.sql` - Add web_sessions table & policies

### Types
- `packages/shared-types/typescript/src/event.ts` - Extend with WebSessionEvent
- `packages/shared-types/python/src/mycelium_shared_types/event.py` - Python equivalent

---

## Testing Checklist

- [ ] EventRecorder captures clicks correctly
- [ ] EventRecorder captures navigation correctly
- [ ] EventRecorder never captures password field values
- [ ] EventRecorder respects maxEvents limit
- [ ] Recording button state transitions work
- [ ] Session review modal displays timeline correctly
- [ ] Workflow detection identifies task creation
- [ ] Workflow detection identifies document ingestion
- [ ] Compression reduces event count significantly
- [ ] LocalStorage saves/loads recordings correctly
- [ ] Ingestion endpoint accepts web_session type
- [ ] SessionProcessor generates markdown summary
- [ ] Agent context includes web session data
- [ ] Privacy redaction works for API keys
- [ ] Privacy checkbox blocks ingestion when unchecked
- [ ] Recordings can be deleted from UI
- [ ] Recordings page shows correct metadata
- [ ] Download JSON exports complete recording
- [ ] Multiple recordings can coexist in localStorage
- [ ] Recording auto-stops after max duration

---

## Documentation Needed

1. **User Guide**: "How to Record and Ingest Web Sessions"
2. **Developer Guide**: "Event Recorder Architecture"
3. **Privacy Policy**: "What Web Session Recording Captures"
4. **API Docs**: Update OpenAPI spec with new endpoints
5. **Workflow Patterns**: Document all detectable workflow patterns

---

## Performance Considerations

1. **Event Storage**:
   - Cap at 500 events per session
   - Use circular buffer to automatically drop oldest
   - Debounce high-frequency events (e.g., mouse moves)

2. **Compression**:
   - Run compression in Web Worker if available
   - Show progress indicator for large sessions
   - Cache compressed results

3. **Ingestion**:
   - Batch event processing on backend
   - Async processing for large sessions
   - Progress feedback to user

4. **Storage**:
   - Monitor localStorage usage (warn at 5MB)
   - Offer auto-cleanup of old recordings
   - Consider IndexedDB for larger recordings

---

## Rollout Plan

### Phase 1 (MVP) - 2-3 weeks
- Core recording infrastructure (frontend)
- Basic UI (button, modal, timeline)
- LocalStorage persistence
- Backend ingestion endpoint
- Session processing & compression
- Manual ingestion flow
- Privacy controls

### Phase 2 - 1-2 weeks
- Supabase sync for recordings
- Enhanced workflow detection
- Insights dashboard
- Settings page integration
- Cross-device sync

### Phase 3 - 1-2 weeks
- Real-time streaming to event bus
- AI-powered summarization
- Advanced visualizations
- Session replay (optional)

### Beta Testing
- Internal team testing first
- 5-10 external beta users
- Iterate based on feedback
- Monitor storage usage

### General Availability
- Documentation complete
- Performance validated
- Privacy audit passed
- Feature flag enabled by default

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Users accidentally record sensitive data | High | Aggressive redaction, privacy warnings, manual review required |
| LocalStorage fills up | Medium | Auto-cleanup, warnings, IndexedDB fallback |
| Performance impact on web app | Medium | Debouncing, efficient event handlers, Web Workers |
| Users don't understand feature | Medium | Clear onboarding, examples, documentation |
| Backend processing too slow | Low | Async processing, progress indicators |
| Recordings not useful to agents | Medium | Iterative improvement of compression/summarization |

---

## Open Questions to Resolve During Implementation

1. **Compression Strategy**: Should we use LLM for compression or heuristic-based? (Recommend: Start heuristic, add LLM in Phase 2)
2. **Storage Location**: LocalStorage vs IndexedDB vs Supabase? (Recommend: Start localStorage, add Supabase sync in Phase 2)
3. **Event Granularity**: How detailed should events be? (Recommend: Capture everything, compress aggressively)
4. **Workflow Detection**: How many workflows to detect? (Recommend: Start with 3-5 common patterns, expand later)
5. **Real-Time Streaming**: Phase 1 or Phase 2? (Recommend: Phase 2, focus on manual flow first)
6. **UI Location**: Fixed button vs sidebar vs menu? (Recommend: Fixed top-right, consistent across all pages)
7. **Auto-Stop**: Should recordings auto-stop after X minutes? (Recommend: Yes, 30 minutes default, configurable)
8. **Cross-User**: Should admins see other users' recordings? (Recommend: No, privacy violation)

---

## Summary for Implementation

This document provides a complete blueprint for adding a web-based event recording system to Mycelium. The feature:

1. **Captures** user interactions in the web app with privacy-first design
2. **Compresses** events into meaningful summaries and detected workflows
3. **Stores** recordings locally with optional cloud sync
4. **Ingests** recordings through existing ingestion pipeline
5. **Provides** rich context to agents through enhanced context system
6. **Respects** user privacy with explicit consent and aggressive redaction

The implementation follows Mycelium's existing patterns:
- Uses existing `MyceliumEvent` schema as foundation
- Integrates with current ingestion system (`IngestionService`)
- Follows design system in `globals.css`
- Extends current UI patterns (cards, badges, modals)
- Aligns with event bus architecture (optional Phase 2)

**Start with Phase 1 (MVP)** to validate user adoption and context usefulness, then expand to Phases 2-3 based on feedback.
