// Thin API wrapper. Falls back to mock data when the API is unreachable.
import { API_BASE } from "@/config";
import { mockStatus, mockSessions, mockMemory, mockBriefing, mockSettings, type Status, type Session, type MemoryChunk, type Briefing, type Settings } from "./mockData";

function apiUrl(path: string): string {
  const base = API_BASE.replace(/\/$/, "");
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${base}${p}`;
}

async function tryFetch<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(apiUrl(path), { signal: AbortSignal.timeout(1500) });
    if (!res.ok) throw new Error(String(res.status));
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

async function tryDelete(path: string): Promise<{ ok: boolean; status: number | null }> {
  try {
    const res = await fetch(apiUrl(path), {
      method: "DELETE",
      signal: AbortSignal.timeout(2000),
    });
    return { ok: res.ok, status: res.status };
  } catch {
    // Backend unreachable — treat as soft-success so UI stays usable in mock mode.
    return { ok: true, status: null };
  }
}

export const api = {
  getStatus: () => tryFetch<Status>("/status", mockStatus),
  getSessions: () => tryFetch<Session[]>("/sessions", mockSessions),
  getMemory: () => tryFetch<MemoryChunk[]>("/memory", mockMemory),
  getBriefing: () => tryFetch<Briefing | null>("/briefing/today", mockBriefing),
  getSettings: () => tryFetch<Settings>("/settings", mockSettings),
  deleteMemoryChunk: (chunkId: string) => tryDelete(`/memory/chunks/${chunkId}`),
};
