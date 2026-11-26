import { Collapsible } from "@base-ui/react/collapsible";
import { ChevronRight } from "lucide-react";
import React from "react";
import { cn } from "../../lib/cn";

/** 可折叠区块：标题行 + 内容。收起时内容保留在页面里（只是隐藏），里面没保存的输入不会丢 */
export const Disclosure: React.FC<{
  title: React.ReactNode;
  meta?: React.ReactNode;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  size?: "lg" | "sm";
  className?: string;
  children: React.ReactNode;
}> = ({ title, meta, open, defaultOpen, onOpenChange, size = "lg", className, children }) => (
  <Collapsible.Root open={open} defaultOpen={defaultOpen} onOpenChange={onOpenChange} className={className}>
    <Collapsible.Trigger
      className={cn(
        "group flex w-full cursor-pointer items-center gap-2.5 rounded-[4px] text-left outline-none focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink",
        size === "sm" && "text-[13px] text-muted hover:text-ink",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "grid flex-none place-items-center transition-transform duration-150 group-data-panel-open:rotate-90",
          size === "lg" && "size-5 rounded-[4px] border-2 border-ink bg-main",
        )}
      >
        <ChevronRight className="size-3.5" strokeWidth={3} />
      </span>
      <span className={size === "lg" ? "text-lg font-black" : "font-semibold"}>{title}</span>
      {meta ? <span className="min-w-0 truncate text-muted">{meta}</span> : null}
    </Collapsible.Trigger>
    <Collapsible.Panel keepMounted className="[&[hidden]:not([hidden='until-found'])]:hidden">
      <div className={size === "lg" ? "pt-4" : "pt-3"}>{children}</div>
    </Collapsible.Panel>
  </Collapsible.Root>
);
