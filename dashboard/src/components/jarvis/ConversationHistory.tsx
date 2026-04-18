import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import type { Session } from "@/lib/mockData";

interface Props {
  sessions: Session[];
}

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toISOString().slice(0, 16).replace("T", " ");
}

export function ConversationHistory({ sessions }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set([sessions[0]?.id]));
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    if (!query.trim()) return sessions;
    const q = query.toLowerCase();
    return sessions.filter(
      (s) =>
        s.id.toLowerCase().includes(q) ||
        s.messages.some((m) => m.text.toLowerCase().includes(q)),
    );
  }, [sessions, query]);

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  return (
    <section className="hud-panel flex flex-col min-h-0">
      <div className="hud-section-header">
        <span>CONVERSATION HISTORY</span>
        <span className="ml-auto font-mono normal-case tracking-normal text-muted-foreground/70">
          {filtered.length} sessions · read-only
        </span>
      </div>

      <div className="p-3 border-b border-hud-border">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="search transcripts..."
            className="h-8 pl-8 bg-background border-hud-border font-mono text-xs rounded-none focus-visible:ring-primary"
          />
        </div>
      </div>

      <div className="divide-y divide-hud-border overflow-y-auto">
        {filtered.map((s) => {
          const isOpen = expanded.has(s.id);
          const preview = s.messages.find((m) => m.role === "user")?.text ?? "";
          return (
            <div key={s.id}>
              <button
                onClick={() => toggle(s.id)}
                className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-panel-elevated/60 transition-colors text-left"
              >
                {isOpen ? (
                  <ChevronDown className="w-3 h-3 text-primary shrink-0" />
                ) : (
                  <ChevronRight className="w-3 h-3 text-muted-foreground shrink-0" />
                )}
                <span className="font-mono text-[11px] text-muted-foreground tabular-nums shrink-0">
                  {formatDate(s.startedAt)}
                </span>
                <span className="font-mono text-[11px] text-primary/70 shrink-0">{s.id}</span>
                <span className="text-xs text-foreground/70 truncate flex-1">{preview}</span>
                <span className="font-mono text-[10px] text-muted-foreground shrink-0">
                  {s.messageCount} msg · {s.tokenCount} tok
                </span>
              </button>

              {isOpen && (
                <div className="px-4 pb-4 pt-1 space-y-2 bg-background/40">
                  {s.messages.map((m, i) => (
                    <div
                      key={i}
                      className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
                    >
                      <div className={`max-w-[78%] ${m.role === "user" ? "items-end" : "items-start"} flex flex-col gap-0.5`}>
                        <span className="hud-label">
                          {m.role === "user" ? "USER" : "JARVIS"} · {m.ts}
                        </span>
                        {m.role === "user" ? (
                          <div className="px-3 py-2 bg-primary text-primary-foreground text-sm">
                            {m.text}
                          </div>
                        ) : (
                          <div className="px-3 py-2 bg-panel-elevated border-l-2 border-primary/60 font-mono text-xs text-foreground/90 whitespace-pre-line">
                            <span className="text-primary mr-1">&gt;</span>
                            {m.text}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {filtered.length === 0 && (
          <div className="p-8 text-center font-mono text-xs text-muted-foreground">
            No sessions match "{query}".
          </div>
        )}
      </div>
    </section>
  );
}
