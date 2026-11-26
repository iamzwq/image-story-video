import { Check, Info, type LucideIcon, TriangleExclamationPoint, X } from "lucide-react";
import React from "react";
import { cn } from "../../lib/cn";

export type AlertTone = "info" | "ok" | "warn" | "error";

const tones: Record<AlertTone, { box: string; icon: string; Mark: LucideIcon }> = {
  info: { box: "bg-info-soft", icon: "bg-info", Mark: Info },
  ok: { box: "bg-ok-soft", icon: "bg-ok", Mark: Check },
  warn: { box: "bg-warn-soft", icon: "bg-warn", Mark: TriangleExclamationPoint },
  error: { box: "bg-danger-soft", icon: "bg-danger", Mark: X },
};

export const Alert: React.FC<{
  tone?: AlertTone;
  onClose?: () => void;
  className?: string;
  children: React.ReactNode;
}> = ({ tone = "info", onClose, className, children }) => {
  const t = tones[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-3 rounded-base border-2 border-ink px-3.5 py-2.5 shadow-brutal-sm",
        t.box,
        className,
      )}
    >
      <span
        aria-hidden
        className={cn("mt-0.5 grid size-5 flex-none place-items-center rounded-full border-2 border-ink", t.icon)}
      >
        <t.Mark className="size-3" strokeWidth={3} />
      </span>
      <div className="min-w-0 flex-1">{children}</div>
      {onClose ? (
        <button
          type="button"
          aria-label="关闭"
          className="-mr-1 grid size-6 flex-none cursor-pointer place-items-center rounded-sm hover:bg-ink hover:text-white pointer-coarse:size-11"
          onClick={onClose}
        >
          <X className="size-4" strokeWidth={2.5} />
        </button>
      ) : null}
    </div>
  );
};
