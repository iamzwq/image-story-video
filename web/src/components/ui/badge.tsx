import { LoaderCircle } from "lucide-react";
import React from "react";
import { cn } from "../../lib/cn";

export type Tone = "muted" | "accent" | "ok" | "warn" | "danger" | "info";

const tones: Record<Tone, string> = {
  muted: "bg-white",
  accent: "bg-main",
  ok: "bg-ok",
  warn: "bg-warn",
  danger: "bg-danger",
  info: "bg-info",
};

export const Badge: React.FC<{ tone?: Tone; className?: string; children: React.ReactNode }> = ({
  tone = "muted",
  className,
  children,
}) => (
  <span
    className={cn(
      "inline-flex max-w-full items-center gap-1 overflow-hidden rounded-full border-2 border-ink px-2 text-xs leading-5 font-bold text-ellipsis whitespace-nowrap text-ink [&_svg]:size-3 [&_svg]:shrink-0",
      tones[tone],
      className,
    )}
  >
    {children}
  </span>
);

const chipTones: Record<"accent" | "plain" | "warn", string> = {
  accent: "bg-main-soft",
  plain: "bg-white",
  warn: "bg-warn-soft",
};

export const Chip: React.FC<{ tone?: keyof typeof chipTones; className?: string; children: React.ReactNode }> = ({
  tone = "accent",
  className,
  children,
}) => (
  <span
    className={cn(
      "inline-flex items-center gap-1 rounded-full border-2 border-ink px-2.5 text-xs leading-5 font-semibold [&_svg]:size-3 [&_svg]:shrink-0",
      chipTones[tone],
      className,
    )}
  >
    {children}
  </span>
);

export const Spinner: React.FC<{ className?: string }> = ({ className }) => (
  <LoaderCircle className={cn("size-3.5 flex-none animate-spin motion-reduce:animate-none", className)} aria-label="运行中" />
);
