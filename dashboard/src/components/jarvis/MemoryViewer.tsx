import { useEffect, useMemo, useState } from "react";
import { Search, Trash2, Database, Check, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { toast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import type { MemoryChunk } from "@/lib/mockData";

interface Props {
  chunks: MemoryChunk[];
  totalCount: number;
}

function relativeDate(iso: string) {
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (d === 0) return "today";
  if (d === 1) return "1d ago";
  return `${d}d ago`;
}

export function MemoryViewer({ chunks, totalCount }: Props) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState(chunks);
  const [deleting, setDeleting] = useState<Set<string>>(new Set());
  const [flashing, setFlashing] = useState<Set<string>>(new Set());

  useEffect(() => {
    setItems(chunks);
  }, [chunks]);

  const filtered = useMemo(() => {
    if (!query.trim()) return items;
    const q = query.toLowerCase();
    return items.filter(
      (c) =>
        c.text.toLowerCase().includes(q) ||
        c.tags.some((t) => t.toLowerCase().includes(q)) ||
        c.id.toLowerCase().includes(q),
    );
  }, [items, query]);

  const handleDelete = async (id: string) => {
    if (deleting.has(id) || flashing.has(id)) return;
    setDeleting((prev) => new Set(prev).add(id));

    const { ok, status } = await api.deleteMemoryChunk(id);

    setDeleting((prev) => {
      const n = new Set(prev);
      n.delete(id);
      return n;
    });

    if (!ok) {
      toast({
        title: "Delete failed",
        description: `${id} · ${status ?? "network error"}`,
        variant: "destructive",
      });
      return;
    }

    setFlashing((prev) => new Set(prev).add(id));
    setTimeout(() => {
      setItems((prev) => prev.filter((c) => c.id !== id));
      setFlashing((prev) => {
        const n = new Set(prev);
        n.delete(id);
        return n;
      });
      toast({ title: "Memory chunk deleted", description: id });
    }, 650);
  };

  return (
    <aside className="hud-panel flex flex-col min-h-0">
      <div className="hud-section-header">
        <span>MEMORY · CHROMADB</span>
        <span className="ml-auto font-mono normal-case tracking-normal text-muted-foreground/70 flex items-center gap-1">
          <Database className="w-3 h-3" />
          {totalCount} chunks
        </span>
      </div>

      <div className="p-3 border-b border-hud-border space-y-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="similarity query..."
            className="h-8 pl-8 bg-background border-hud-border font-mono text-xs rounded-none focus-visible:ring-primary"
          />
        </div>
        <div className="hud-label">
          {filtered.length} / {items.length} shown
        </div>
      </div>

      <div className="overflow-y-auto divide-y divide-hud-border">
        {filtered.map((c) => {
          const isFlashing = flashing.has(c.id);
          const isDeleting = deleting.has(c.id);
          return (
            <div
              key={c.id}
              className={`relative p-3 group transition-all duration-500 ${
                isFlashing
                  ? "bg-destructive/15 opacity-0 -translate-x-2"
                  : "hover:bg-panel-elevated/50"
              }`}
            >
              {isFlashing && (
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
                  <span className="font-mono text-[10px] uppercase tracking-widest text-destructive border border-destructive/60 bg-background/80 px-2 py-0.5 flex items-center gap-1">
                    <Check className="w-3 h-3" />
                    deleted
                  </span>
                </div>
              )}
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px] text-primary">{c.id}</span>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {relativeDate(c.storedAt)}
                  </span>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={isDeleting || isFlashing}
                  className="h-6 w-6 opacity-0 group-hover:opacity-100 hover:bg-destructive/20 hover:text-destructive rounded-none disabled:opacity-50"
                  onClick={() => handleDelete(c.id)}
                  aria-label={`Delete ${c.id}`}
                >
                  {isDeleting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                </Button>
              </div>
              <p className="font-mono text-[11px] text-foreground/85 leading-relaxed mb-2 line-clamp-3">
                {c.text}
              </p>
              <div className="flex flex-wrap gap-1">
                {c.tags.map((t) => {
                  const isScore = /^[\d.]+$/.test(t);
                  return (
                    <span
                      key={t}
                      className={`font-mono text-[9px] uppercase tracking-wider px-1.5 py-0.5 border ${
                        isScore
                          ? "border-primary/40 text-primary bg-primary/10"
                          : "border-hud-border-strong text-muted-foreground"
                      }`}
                    >
                      {t}
                    </span>
                  );
                })}
              </div>
            </div>
          );
        })}

        {filtered.length === 0 && (
          <div className="p-8 text-center font-mono text-xs text-muted-foreground">
            No chunks match.
          </div>
        )}
      </div>
    </aside>
  );
}
