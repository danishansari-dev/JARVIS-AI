import { useEffect, useState } from "react";
import { StatusBar } from "@/components/jarvis/StatusBar";
import { BriefingCard } from "@/components/jarvis/BriefingCard";
import { ConversationHistory } from "@/components/jarvis/ConversationHistory";
import { MemoryViewer } from "@/components/jarvis/MemoryViewer";
import { SettingsDrawer } from "@/components/jarvis/SettingsDrawer";
import { API_BASE } from "@/config";
import { api } from "@/lib/api";
import {
  mockStatus,
  mockBriefing,
  mockMemory,
  mockMemoryCount,
  mockSessions,
  mockSettings,
  type Status,
  type Briefing,
  type MemoryChunk,
  type Session,
  type Settings,
} from "@/lib/mockData";

const Index = () => {
  const [status, setStatus] = useState<Status>(mockStatus);
  const [briefing, setBriefing] = useState<Briefing | null>(mockBriefing);
  const [memory, setMemory] = useState<MemoryChunk[]>(mockMemory);
  const [sessions, setSessions] = useState<Session[]>(mockSessions);
  const [settings, setSettings] = useState<Settings>(mockSettings);

  useEffect(() => {
    document.title = "JARVIS · Personal AI Console";
    const meta = document.querySelector('meta[name="description"]');
    if (meta) meta.setAttribute("content", "JARVIS HUD — personal AI assistant control console: status, conversation history, memory and settings.");

    (async () => {
      const [s, b, m, ss, set] = await Promise.all([
        api.getStatus(),
        api.getBriefing(),
        api.getMemory(),
        api.getSessions(),
        api.getSettings(),
      ]);
      setStatus(s);
      setBriefing(b);
      setMemory(m);
      setSessions(ss);
      setSettings(set);
    })();
  }, []);

  return (
    <div className="min-h-screen bg-background flex flex-col scanline-bg">
      <StatusBar
        status={status}
        model={settings.defaultModel}
        onToggleOnline={(v) => setStatus((s) => ({ ...s, online: v }))}
      />

      <main className="flex-1 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px] gap-3 p-3">
        <div className="flex flex-col gap-3 min-h-0">
          <BriefingCard briefing={briefing} />
          <ConversationHistory sessions={sessions} />
        </div>

        <MemoryViewer chunks={memory} totalCount={mockMemoryCount} />
      </main>

      <footer className="border-t border-hud-border bg-panel px-4 py-1.5 flex items-center justify-between font-mono text-[10px] text-muted-foreground">
        <span>
          API · <span className="text-foreground/90">{API_BASE}</span> ·{" "}
          <span className="text-success">connected</span>
        </span>
        <span className="blink-cursor">ready</span>
      </footer>

      <SettingsDrawer settings={settings} onChange={setSettings} />
    </div>
  );
};

export default Index;
