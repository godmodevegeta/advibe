import { useEffect, useId, useRef, useState } from "react";
import { ArrowUpRight, ChevronLeft, ChevronRight } from "lucide-react";
import type { Preset } from "./types";

export function PresetSelector({
  presets,
  busy,
  onSelect,
}: {
  presets: Preset[];
  busy: boolean;
  onSelect: (prompt: string) => void;
}) {
  const [active, setActive] = useState<Preset | null>(null);
  const [visible, setVisible] = useState(false);
  const previewId = useId();
  const track = useRef<HTMLDivElement>(null);
  const [canPrevious, setCanPrevious] = useState(false);
  const [canNext, setCanNext] = useState(presets.length > 3);
  function updateNavigation() {
    const el = track.current;
    if (!el || !el.clientWidth) return;
    setCanPrevious(el.scrollLeft > 2);
    setCanNext(el.scrollLeft + el.clientWidth < el.scrollWidth - 2);
  }
  useEffect(() => {
    updateNavigation();
    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(updateNavigation)
        : undefined;
    if (track.current) observer?.observe(track.current);
    window.addEventListener("resize", updateNavigation);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", updateNavigation);
    };
  }, [presets.length]);
  const hovered = useRef<Preset | null>(null);
  const focused = useRef<Preset | null>(null);
  const overPreview = useRef(false);
  const dismissed = useRef(false);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const cancelClose = () => clearTimeout(closeTimer.current);
  useEffect(() => () => clearTimeout(closeTimer.current), []);

  function show(preset: Preset) {
    cancelClose();
    dismissed.current = false;
    setActive(preset);
    setVisible(true);
  }
  function closeSoon() {
    cancelClose();
    closeTimer.current = setTimeout(() => {
      if (dismissed.current || overPreview.current) return;
      const next = hovered.current || focused.current;
      if (next) show(next);
      else setVisible(false);
    }, 150);
  }
  function dismiss() {
    cancelClose();
    dismissed.current = true;
    setVisible(false);
  }
  function browse(direction: number) {
    dismiss();
    hovered.current = null;
    focused.current = null;
    track.current?.scrollBy({
      left: direction * track.current.clientWidth,
      behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
    });
  }

  return (
    <div
      className="preset-selector"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          dismiss();
          e.stopPropagation();
        }
      }}
    >
      <div
        className="preset-carousel-row"
        role="group"
        aria-label="Campaign presets"
      >
        <button
          className={`preset-navigation ${canPrevious ? "" : "is-hidden"}`}
          aria-label="Previous presets"
          disabled={busy || !canPrevious}
          onFocus={dismiss}
          onPointerEnter={dismiss}
          onClick={() => browse(-1)}
        >
          <ChevronLeft size={18} />
        </button>
        <div
          className="preset-list"
          ref={track}
          onScroll={() => {
            updateNavigation();
            if (focused.current) show(focused.current);
            else dismiss();
          }}
        >
          {presets.map((p) => (
            <button
              key={p.id}
              disabled={busy}
              aria-describedby={
                visible && active?.id === p.id ? previewId : undefined
              }
              onPointerEnter={(e) => {
                if (e.pointerType !== "touch") {
                  hovered.current = p;
                  show(p);
                }
              }}
              onPointerLeave={(e) => {
                if (e.pointerType !== "touch") {
                  hovered.current = null;
                  closeSoon();
                }
              }}
              onFocus={() => {
                focused.current = p;
                show(p);
              }}
              onBlur={() => {
                focused.current = null;
                closeSoon();
              }}
              onClick={() => {
                dismiss();
                onSelect(p.prompt);
              }}
            >
              {p.title}
              <ArrowUpRight size={15} />
            </button>
          ))}
        </div>
        <button
          className="preset-navigation"
          aria-label="Next presets"
          disabled={busy || !canNext}
          onFocus={dismiss}
          onPointerEnter={dismiss}
          onClick={() => browse(1)}
        >
          <ChevronRight size={18} />
        </button>
      </div>
      <div
        className={`preset-preview ${visible ? "is-visible" : ""}`}
        id={previewId}
        role="tooltip"
        aria-hidden={!visible}
        onPointerEnter={(e) => {
          if (e.pointerType !== "touch") {
            overPreview.current = true;
            cancelClose();
          }
        }}
        onPointerLeave={() => {
          overPreview.current = false;
          closeSoon();
        }}
      >
        <span className="eyebrow">PRESET PROMPT</span>
        <h3>{active?.title}</h3>
        <p>{active?.prompt}</p>
      </div>
    </div>
  );
}
