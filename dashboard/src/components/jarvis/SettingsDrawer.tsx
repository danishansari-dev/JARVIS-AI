import { useState } from "react";
import { Settings as SettingsIcon, Plus, X } from "lucide-react";
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from "@/components/ui/drawer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "@/hooks/use-toast";
import type { Settings, Model } from "@/lib/mockData";

interface Props {
  settings: Settings;
  onChange: (s: Settings) => void;
}

const TIMEZONES = [
  "Europe/Lisbon",
  "Europe/London",
  "Europe/Berlin",
  "America/New_York",
  "America/Los_Angeles",
  "Asia/Tokyo",
];

export function SettingsDrawer({ settings, onChange }: Props) {
  const [draft, setDraft] = useState<Settings>(settings);
  const [open, setOpen] = useState(false);

  const update = <K extends keyof Settings>(k: K, v: Settings[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));

  const updateShortcut = (i: number, field: "alias" | "path", v: string) => {
    setDraft((d) => ({
      ...d,
      shortcuts: d.shortcuts.map((s, idx) => (idx === i ? { ...s, [field]: v } : s)),
    }));
  };

  const addShortcut = () =>
    setDraft((d) => ({ ...d, shortcuts: [...d.shortcuts, { alias: "", path: "" }] }));

  const removeShortcut = (i: number) =>
    setDraft((d) => ({ ...d, shortcuts: d.shortcuts.filter((_, idx) => idx !== i) }));

  const save = () => {
    onChange(draft);
    toast({ title: "Settings saved", description: "Configuration synchronised." });
    setOpen(false);
  };

  return (
    <Drawer open={open} onOpenChange={setOpen}>
      <DrawerTrigger asChild>
        <Button
          variant="outline"
          className="fixed bottom-4 right-4 z-40 h-10 px-4 rounded-none border-hud-border-strong bg-panel hover:bg-panel-elevated hover:border-primary font-mono text-xs uppercase tracking-[0.2em] gap-2"
        >
          <SettingsIcon className="w-4 h-4" />
          Settings
        </Button>
      </DrawerTrigger>

      <DrawerContent className="bg-panel border-hud-border-strong rounded-t-none max-h-[88vh]">
        <DrawerHeader className="border-b border-hud-border">
          <DrawerTitle className="font-mono text-xs uppercase tracking-[0.25em] text-foreground flex items-center gap-2">
            <span className="block w-1 h-3 bg-primary" />
            System Configuration
          </DrawerTitle>
        </DrawerHeader>

        <div className="overflow-y-auto p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Profile */}
          <div className="space-y-4">
            <div className="hud-label">PROFILE</div>
            <Field label="Name">
              <Input
                value={draft.name}
                onChange={(e) => update("name", e.target.value)}
                className="h-9 bg-background border-hud-border rounded-none font-mono text-xs"
              />
            </Field>
            <Field label="Timezone">
              <Select value={draft.timezone} onValueChange={(v) => update("timezone", v)}>
                <SelectTrigger className="h-9 bg-background border-hud-border rounded-none font-mono text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIMEZONES.map((tz) => (
                    <SelectItem key={tz} value={tz} className="font-mono text-xs">
                      {tz}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="City (weather)">
              <Input
                value={draft.city}
                onChange={(e) => update("city", e.target.value)}
                className="h-9 bg-background border-hud-border rounded-none font-mono text-xs"
              />
            </Field>
          </div>

          {/* AI / Voice */}
          <div className="space-y-4">
            <div className="hud-label">AI & VOICE</div>
            <Field label="Default model">
              <div className="flex border border-hud-border">
                {(["haiku", "sonnet"] as Model[]).map((m) => (
                  <button
                    key={m}
                    onClick={() => update("defaultModel", m)}
                    className={`flex-1 h-9 font-mono text-xs uppercase tracking-wider transition-colors ${
                      draft.defaultModel === m
                        ? "bg-primary text-primary-foreground"
                        : "bg-background text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </Field>

            <Field label={`TTS speed · ${draft.ttsSpeed.toFixed(2)}x`}>
              <div className="px-1 pt-2">
                <Slider
                  value={[draft.ttsSpeed]}
                  onValueChange={([v]) => update("ttsSpeed", Math.round(v * 100) / 100)}
                  min={0.8}
                  max={1.2}
                  step={0.05}
                />
                <div className="flex justify-between mt-1 font-mono text-[10px] text-muted-foreground">
                  <span>0.80x</span>
                  <span>1.00x</span>
                  <span>1.20x</span>
                </div>
              </div>
            </Field>

            <Field label="Morning briefing time">
              <Input
                type="time"
                value={draft.briefingTime}
                onChange={(e) => update("briefingTime", e.target.value)}
                className="h-9 bg-background border-hud-border rounded-none font-mono text-xs"
              />
            </Field>

            <Field label="Proactive notifications">
              <div className="flex items-center gap-3 h-9">
                <Switch
                  checked={draft.proactiveNotifications}
                  onCheckedChange={(v) => update("proactiveNotifications", v)}
                />
                <span className="font-mono text-xs text-muted-foreground">
                  {draft.proactiveNotifications ? "ENABLED" : "DISABLED"}
                </span>
              </div>
            </Field>
          </div>

          {/* Shortcuts */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="hud-label">APP LAUNCH SHORTCUTS</div>
              <Button
                variant="ghost"
                size="sm"
                onClick={addShortcut}
                className="h-7 rounded-none font-mono text-[10px] uppercase tracking-wider hover:bg-primary/10 hover:text-primary"
              >
                <Plus className="w-3 h-3 mr-1" />
                Add
              </Button>
            </div>
            <div className="border border-hud-border divide-y divide-hud-border">
              {draft.shortcuts.map((s, i) => (
                <div key={i} className="flex items-center gap-1 p-1.5">
                  <Input
                    value={s.alias}
                    onChange={(e) => updateShortcut(i, "alias", e.target.value)}
                    placeholder="alias"
                    className="h-7 w-24 bg-background border-hud-border rounded-none font-mono text-[11px]"
                  />
                  <span className="font-mono text-muted-foreground text-xs">→</span>
                  <Input
                    value={s.path}
                    onChange={(e) => updateShortcut(i, "path", e.target.value)}
                    placeholder="C:/path/to/app.exe"
                    className="h-7 flex-1 bg-background border-hud-border rounded-none font-mono text-[11px]"
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => removeShortcut(i)}
                    className="h-7 w-7 rounded-none hover:bg-destructive/20 hover:text-destructive"
                  >
                    <X className="w-3 h-3" />
                  </Button>
                </div>
              ))}
              {draft.shortcuts.length === 0 && (
                <div className="p-4 text-center font-mono text-[11px] text-muted-foreground">
                  No shortcuts defined.
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="border-t border-hud-border p-4 flex justify-end gap-2">
          <Button
            variant="ghost"
            onClick={() => setOpen(false)}
            className="rounded-none font-mono text-xs uppercase tracking-wider"
          >
            Cancel
          </Button>
          <Button
            onClick={save}
            className="rounded-none font-mono text-xs uppercase tracking-wider bg-primary hover:bg-primary-glow"
          >
            Save Configuration
          </Button>
        </div>
      </DrawerContent>
    </Drawer>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="hud-label">{label}</div>
      {children}
    </div>
  );
}
