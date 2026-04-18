import { useState } from "react";
import { ChevronDown, ChevronRight, Calendar, Cloud } from "lucide-react";
import type { Briefing } from "@/lib/mockData";

interface Props {
  briefing: Briefing | null;
}

export function BriefingCard({ briefing }: Props) {
  const [open, setOpen] = useState(true);

  if (!briefing) {
    return (
      <section className="hud-panel">
        <div className="hud-section-header">MORNING BRIEFING</div>
        <div className="p-6 text-center font-mono text-xs text-muted-foreground">
          No briefing generated for today.
        </div>
      </section>
    );
  }

  return (
    <section className="hud-panel">
      <button
        onClick={() => setOpen(!open)}
        className="w-full hud-section-header hover:bg-panel-elevated/70 transition-colors cursor-pointer"
      >
        <span>MORNING BRIEFING</span>
        <span className="font-mono text-muted-foreground/70 normal-case tracking-normal">
          / {briefing.date}
        </span>
        <span className="ml-auto">
          {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        </span>
      </button>

      {open && (
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3 pb-3 border-b border-hud-border">
            <div className="flex items-start gap-2">
              <Cloud className="w-3.5 h-3.5 text-primary mt-0.5 shrink-0" />
              <div>
                <div className="hud-label mb-0.5">WEATHER</div>
                <div className="font-mono text-xs text-foreground/90">{briefing.weather}</div>
              </div>
            </div>
            <div className="flex items-start gap-2">
              <Calendar className="w-3.5 h-3.5 text-primary mt-0.5 shrink-0" />
              <div>
                <div className="hud-label mb-0.5">CALENDAR</div>
                <div className="font-mono text-xs text-foreground/90">
                  {briefing.calendarCount} events scheduled
                </div>
              </div>
            </div>
          </div>

          <ul className="space-y-1.5">
            {briefing.bullets.map((b, i) => (
              <li key={i} className="flex gap-2 font-mono text-xs text-foreground/85">
                <span className="text-primary shrink-0">▸</span>
                <span>{b}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
