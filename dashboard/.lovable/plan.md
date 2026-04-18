
# JARVIS Dashboard — Plan

A dark, dense, terminal/HUD-style desktop dashboard for a personal AI assistant. Static frontend with realistic placeholder data; API base URL comes from `src/config.ts` (`VITE_API_URL` / default).

## Layout
Single-page desktop dashboard (`/`), CSS grid:

```
┌─────────────────────────────────────────────────────────────┐
│  STATUS BAR  (online toggle • model • TTS quota • uptime)  │
├──────────────────────────────────┬──────────────────────────┤
│                                  │                          │
│  BRIEFING CARD                   │   MEMORY VIEWER          │
│  CONVERSATION HISTORY            │   (ChromaDB chunks)      │
│  (expandable transcripts)        │   search + delete        │
│                                  │                          │
├──────────────────────────────────┴──────────────────────────┤
│  ⚙ SETTINGS  (bottom drawer, opens upward)                  │
└─────────────────────────────────────────────────────────────┘
```

## Visual language
- Background `#0d0d0d`, panels `#121212` with 1px `#1f1f1f` borders, no rounded pastels — square/2px corners only.
- Accent blue `#1a6cf5` for active states, user bubbles, focus rings, online indicator.
- Monospace (JetBrains Mono / ui-monospace) for JARVIS responses, timestamps, IDs, quotas. Sans-serif (Inter) for UI chrome and user messages.
- Dense typography (12–13px body), thin dividers, uppercase micro-labels, blinking cursor accents, scanline-feel section headers.
- All colors wired through `index.css` HSL tokens + `tailwind.config.ts` (no hard-coded hex in components).

## Sections

**1. Status Bar (top, sticky)**
- Left: `JARVIS` wordmark + pulsing dot, online/offline toggle (switch).
- Middle: model selector chip (Haiku / Sonnet) — read-only display synced with Settings.
- Right: ElevenLabs quota `2,340 / 10,000` with thin progress bar; uptime `03:14:27` ticking live.

**2. Briefing Card**
- Compact panel above conversations: date, weather line, calendar count, headline bullets. Collapsible. Empty-state: "No briefing generated for today."

**3. Conversation History (main, read-only)**
- Vertical list of sessions: timestamp, message count, first user message preview, token count.
- Click row → expands inline transcript.
- User messages: right-aligned, blue bg, sans-serif.
- JARVIS messages: left-aligned, gray bg, monospace, with `> ` prefix.
- Filter bar: date range + text search across transcripts.

**4. Memory Viewer (right sidebar)**
- Search box at top (queries memory by similarity — mocked).
- Scrollable list of ChromaDB chunks: 2–3 line text preview, stored date, similarity tag chips (e.g. `work`, `preferences`, `0.87`), delete (trash) icon with confirm.
- Counter: `247 chunks indexed`.

**5. Settings (bottom drawer)**
- Trigger: `⚙ SETTINGS` button fixed bottom-right; opens shadcn `Drawer` from bottom.
- Fields: name, timezone (select), city; default model toggle (Haiku/Sonnet); TTS speed slider 0.8–1.2 with live value; morning briefing time picker; proactive notifications switch.
- App launch shortcuts: editable key→path table (add/remove rows), e.g. `spotify` → `C:/Users/.../Spotify.exe`.
- Save button (toasts "Settings saved" — local state only).

## Data
A single `src/lib/mockData.ts` exports realistic placeholders: status, 6–8 sessions with multi-turn transcripts, today's briefing, ~12 memory chunks, default settings, 4 app shortcuts. A thin `src/lib/api.ts` wraps fetches using `API_BASE` from `src/config.ts` with try/catch fallback to mock data.

## Files
- `src/index.css`, `tailwind.config.ts` — dark HUD tokens, mono font family.
- `src/pages/Index.tsx` — grid layout assembling all sections.
- `src/components/jarvis/StatusBar.tsx`
- `src/components/jarvis/BriefingCard.tsx`
- `src/components/jarvis/ConversationHistory.tsx`
- `src/components/jarvis/MemoryViewer.tsx`
- `src/components/jarvis/SettingsDrawer.tsx`
- `src/lib/mockData.ts`, `src/lib/api.ts`

Reuses shadcn `switch`, `slider`, `drawer`, `select`, `input`, `button`, `scroll-area`, `badge`, `tooltip`.
