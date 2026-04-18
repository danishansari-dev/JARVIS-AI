import { useEffect, useState } from "react";
import { Switch } from "@/components/ui/switch";
import type { Status, Model } from "@/lib/mockData";

interface Props {
  status: Status;
  onToggleOnline: (v: boolean) => void;
  model: Model;
}

function formatUptime(bootedAt: string) {
  const ms = Date.now() - new Date(bootedAt).getTime();
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function StatusBar({ status, onToggleOnline, model }: Props) {
  const [uptime, setUptime] = useState(formatUptime(status.bootedAt));

  useEffect(() => {
    const t = setInterval(() => setUptime(formatUptime(status.bootedAt)), 1000);
    return () => clearInterval(t);
  }, [status.bootedAt]);

  const pct = (status.ttsCharsUsed / status.ttsCharsLimit) * 100;

  return (
    <header className="hud-panel border-l-0 border-r-0 border-t-0 sticky top-0 z-30 backdrop-blur bg-panel/95">
      <div className="flex items-center justify-between px-4 h-12">
        {/* Left: brand + online */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className={`pulse-dot ${status.online ? "" : "offline"}`} />
            <span className="font-mono text-sm font-semibold tracking-[0.25em] text-foreground">
              JARVIS
            </span>
            <span className="font-mono text-[10px] text-muted-foreground">v0.4.1</span>
          </div>

          <div className="h-5 w-px bg-hud-border" />

          <div className="flex items-center gap-2">
            <span className="hud-label">SYSTEM</span>
            <Switch checked={status.online} onCheckedChange={onToggleOnline} />
            <span className={`font-mono text-xs ${status.online ? "text-success" : "text-muted-foreground"}`}>
              {status.online ? "ONLINE" : "OFFLINE"}
            </span>
          </div>
        </div>

        {/* Middle: model */}
        <div className="flex items-center gap-2 border border-hud-border px-3 py-1">
          <span className="hud-label">MODEL</span>
          <span className="font-mono text-xs text-primary uppercase">claude-{model}</span>
        </div>

        {/* Right: quota + uptime */}
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3">
            <span className="hud-label">11LABS</span>
            <div className="flex items-center gap-2">
              <div className="w-24 h-1 bg-hud-border relative">
                <div
                  className="absolute inset-y-0 left-0 bg-primary"
                  style={{ width: `${Math.min(pct, 100)}%` }}
                />
              </div>
              <span className="font-mono text-[11px] text-foreground/80 tabular-nums">
                {status.ttsCharsUsed.toLocaleString()} / {status.ttsCharsLimit.toLocaleString()}
              </span>
            </div>
          </div>

          <div className="h-5 w-px bg-hud-border" />

          <div className="flex items-center gap-2">
            <span className="hud-label">UPTIME</span>
            <span className="font-mono text-xs text-foreground tabular-nums">{uptime}</span>
          </div>
        </div>
      </div>
    </header>
  );
}
