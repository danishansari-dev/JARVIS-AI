// Mock data for JARVIS dashboard (fallback when the API from `src/config.ts` is unreachable).

export type Model = "haiku" | "sonnet";

export interface Status {
  online: boolean;
  model: Model;
  ttsCharsUsed: number;
  ttsCharsLimit: number;
  bootedAt: string; // ISO timestamp
}

export interface Message {
  role: "user" | "jarvis";
  text: string;
  ts: string;
}

export interface Session {
  id: string;
  startedAt: string;
  messageCount: number;
  tokenCount: number;
  messages: Message[];
}

export interface MemoryChunk {
  id: string;
  text: string;
  storedAt: string;
  tags: string[];
  similarity?: number;
}

export interface Briefing {
  date: string;
  weather: string;
  calendarCount: number;
  bullets: string[];
}

export interface AppShortcut {
  alias: string;
  path: string;
}

export interface Settings {
  name: string;
  timezone: string;
  city: string;
  defaultModel: Model;
  ttsSpeed: number;
  briefingTime: string;
  proactiveNotifications: boolean;
  shortcuts: AppShortcut[];
}

export const mockStatus: Status = {
  online: true,
  model: "sonnet",
  ttsCharsUsed: 2340,
  ttsCharsLimit: 10000,
  bootedAt: new Date(Date.now() - (3 * 3600 + 14 * 60 + 27) * 1000).toISOString(),
};

export const mockBriefing: Briefing = {
  date: new Date().toISOString().slice(0, 10),
  weather: "Lisbon · 18°C, partly cloudy, 12% rain · wind 14 km/h",
  calendarCount: 3,
  bullets: [
    "Standup at 09:30 — review backend retry logic with M.",
    "Lunch block 13:00–14:00 (no calls scheduled).",
    "Deep work window 15:00–17:30: ChromaDB rerank prototype.",
    "Reminder: pick up dry cleaning before 19:00.",
  ],
};

const sessionTemplate = (id: string, daysAgo: number, messages: Message[]): Session => ({
  id,
  startedAt: new Date(Date.now() - daysAgo * 86400000).toISOString(),
  messageCount: messages.length,
  tokenCount: messages.reduce((s, m) => s + Math.ceil(m.text.length / 4), 0),
  messages,
});

export const mockSessions: Session[] = [
  sessionTemplate("s_8a31", 0, [
    { role: "user", ts: "09:14", text: "What's on my calendar today?" },
    { role: "jarvis", ts: "09:14", text: "Three events: standup at 09:30, lunch block 13:00–14:00, and a deep-work window 15:00–17:30. No external calls. Want me to draft an agenda for the standup?" },
    { role: "user", ts: "09:15", text: "Yeah, three bullets max." },
    { role: "jarvis", ts: "09:15", text: "Drafted:\n  1. Status of ChromaDB rerank prototype.\n  2. Backend retry logic — open question on jitter strategy.\n  3. Blocker: ElevenLabs quota nearing 25% by midday.\nSent to your notes app." },
  ]),
  sessionTemplate("s_8a30", 0, [
    { role: "user", ts: "08:02", text: "Play morning playlist on Spotify." },
    { role: "jarvis", ts: "08:02", text: "Launching Spotify and queuing 'Morning Focus'. 14 tracks, ~58 minutes." },
  ]),
  sessionTemplate("s_8a2e", 1, [
    { role: "user", ts: "21:47", text: "Remind me to call the landlord tomorrow at 10." },
    { role: "jarvis", ts: "21:47", text: "Reminder set for tomorrow 10:00 — \"Call landlord\". I'll proactively notify you 5 minutes before." },
    { role: "user", ts: "21:48", text: "Also store: landlord prefers WhatsApp not phone calls." },
    { role: "jarvis", ts: "21:48", text: "Stored to long-term memory under tags: contacts, preferences. Chunk id mem_4f12." },
  ]),
  sessionTemplate("s_8a2c", 1, [
    { role: "user", ts: "16:33", text: "Summarize the last three emails from Marta." },
    { role: "jarvis", ts: "16:33", text: "1. Contract amendment v3 attached, asks review by Friday.\n2. Confirms Tuesday 11:00 sync.\n3. Forwarded vendor quote — €4,200, 3-week lead time. She wants your call by EOD Wed." },
  ]),
  sessionTemplate("s_8a28", 2, [
    { role: "user", ts: "11:02", text: "How's my ElevenLabs quota looking this month?" },
    { role: "jarvis", ts: "11:02", text: "23.4% consumed (2,340 / 10,000 chars). Projected month-end: 71% based on 7-day rolling average. Comfortable margin." },
  ]),
  sessionTemplate("s_8a25", 3, [
    { role: "user", ts: "19:18", text: "What did I say about the Berlin trip last week?" },
    { role: "jarvis", ts: "19:18", text: "Two relevant chunks:\n  • mem_3a91 (5d ago): \"Berlin trip booked Apr 18–22, Hotel Oderberger.\"\n  • mem_3b04 (4d ago): \"Pack the EU adapter, dinner with K. on Friday at 20:00.\"" },
  ]),
  sessionTemplate("s_8a1f", 4, [
    { role: "user", ts: "07:55", text: "Briefing." },
    { role: "jarvis", ts: "07:55", text: "Good morning. 2 calendar events, light load. Weather 16°C drizzle until noon. Top priority per yesterday's notes: finish the retry-logic PR. Anything to add?" },
    { role: "user", ts: "07:56", text: "Add: book dentist." },
    { role: "jarvis", ts: "07:56", text: "Added to today's task list. I'll surface it again at 14:00 if untouched." },
  ]),
];

export const mockMemory: MemoryChunk[] = [
  { id: "mem_4f12", storedAt: new Date(Date.now() - 1 * 86400000).toISOString(), text: "Landlord prefers WhatsApp messages, not phone calls. Response time usually within 2h on weekdays.", tags: ["contacts", "preferences", "0.94"] },
  { id: "mem_4e88", storedAt: new Date(Date.now() - 2 * 86400000).toISOString(), text: "Coffee order: oat flat white, no sugar. Backup: black americano if oat milk unavailable.", tags: ["preferences", "0.91"] },
  { id: "mem_4d31", storedAt: new Date(Date.now() - 3 * 86400000).toISOString(), text: "Quarterly review meeting cadence: every 2nd Wednesday at 14:00 with M. and team leads.", tags: ["work", "calendar", "0.88"] },
  { id: "mem_4c02", storedAt: new Date(Date.now() - 4 * 86400000).toISOString(), text: "Berlin trip: Apr 18–22. Hotel Oderberger, room 312. Dinner with K. on Friday 20:00 at Lokal.", tags: ["travel", "0.86"] },
  { id: "mem_4b77", storedAt: new Date(Date.now() - 5 * 86400000).toISOString(), text: "Pack EU adapter, melatonin, paperback for the flight. Carry-on only, 7kg limit on Ryanair.", tags: ["travel", "checklist", "0.84"] },
  { id: "mem_4a09", storedAt: new Date(Date.now() - 6 * 86400000).toISOString(), text: "Backend retry logic decision: exponential backoff with full jitter, max 5 retries, 30s ceiling.", tags: ["work", "engineering", "0.82"] },
  { id: "mem_4912", storedAt: new Date(Date.now() - 8 * 86400000).toISOString(), text: "Sister's birthday Apr 27. Idea pool: bookstore voucher, ceramics class, weekend hike together.", tags: ["personal", "gifts", "0.79"] },
  { id: "mem_4801", storedAt: new Date(Date.now() - 10 * 86400000).toISOString(), text: "Doctor: Dra. Pereira, Clínica Lapa. Last visit Mar 02. Next routine bloodwork due in October.", tags: ["health", "contacts", "0.77"] },
  { id: "mem_4744", storedAt: new Date(Date.now() - 12 * 86400000).toISOString(), text: "Project Atlas budget approved at €18k. Spend cadence: monthly invoices, NET-30, contact: Sara.", tags: ["work", "finance", "0.74"] },
  { id: "mem_4612", storedAt: new Date(Date.now() - 15 * 86400000).toISOString(), text: "Gym routine: push/pull/legs split, Mon/Wed/Fri 07:00. Avoid evening sessions, sleep impact.", tags: ["health", "routine", "0.71"] },
  { id: "mem_4501", storedAt: new Date(Date.now() - 18 * 86400000).toISOString(), text: "Wine preference: low-intervention, light-bodied reds. Liked: Hidden Sea Pinot, Niepoort Drink Me.", tags: ["preferences", "0.68"] },
  { id: "mem_4411", storedAt: new Date(Date.now() - 22 * 86400000).toISOString(), text: "Reading list: 'The Mom Test', 'Working in Public', 'A Pattern Language'. Started first one.", tags: ["reading", "0.65"] },
];

export const mockMemoryCount = 247;

export const mockSettings: Settings = {
  name: "Daniel",
  timezone: "Europe/Lisbon",
  city: "Lisbon",
  defaultModel: "sonnet",
  ttsSpeed: 1.0,
  briefingTime: "07:30",
  proactiveNotifications: true,
  shortcuts: [
    { alias: "spotify", path: "C:/Users/daniel/AppData/Roaming/Spotify/Spotify.exe" },
    { alias: "vscode", path: "C:/Users/daniel/AppData/Local/Programs/Microsoft VS Code/Code.exe" },
    { alias: "obsidian", path: "C:/Users/daniel/AppData/Local/Obsidian/Obsidian.exe" },
    { alias: "browser", path: "C:/Program Files/Mozilla Firefox/firefox.exe" },
  ],
};
