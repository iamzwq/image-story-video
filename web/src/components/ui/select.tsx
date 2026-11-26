import { Select as BaseSelect } from "@base-ui/react/select";
import { Check, ChevronsUpDown } from "lucide-react";
import React from "react";
import { cn } from "../../lib/cn";

export type SelectItem = { value: string; label: React.ReactNode };

export const Select: React.FC<{
  value: string;
  items: SelectItem[];
  onChange: (value: string) => void;
  disabled?: boolean;
  className?: string;
}> = ({ value, items, onChange, disabled, className }) => (
  <BaseSelect.Root
    items={items}
    value={value}
    disabled={disabled}
    onValueChange={(v) => {
      if (typeof v === "string") {
        onChange(v);
      }
    }}
  >
    <BaseSelect.Trigger
      className={cn(
        "flex h-11 w-full min-w-0 cursor-pointer items-center justify-between gap-2 rounded-base border-2 border-ink bg-white pr-2.5 pl-3 text-left text-sm outline-hidden select-none pointer-coarse:h-13",
        "focus-visible:shadow-brutal-sm data-popup-open:shadow-brutal-sm",
        "data-disabled:cursor-not-allowed data-disabled:bg-paper data-disabled:text-muted",
        className,
      )}
    >
      <BaseSelect.Value className="min-w-0 truncate" />
      <BaseSelect.Icon className="flex-none">
        <ChevronsUpDown className="size-4" strokeWidth={2.5} />
      </BaseSelect.Icon>
    </BaseSelect.Trigger>
    <BaseSelect.Portal>
      <BaseSelect.Positioner className="z-50 outline-hidden select-none" sideOffset={6} alignItemWithTrigger={false}>
        <BaseSelect.Popup
          className={cn(
            "min-w-(--anchor-width) origin-(--transform-origin) rounded-base border-2 border-ink bg-white p-1 shadow-brutal outline-hidden",
            "transition-[scale,opacity] duration-100 data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0",
          )}
        >
          <BaseSelect.List className="max-h-(--available-height) overflow-y-auto">
            {items.map((item) => (
              <BaseSelect.Item
                key={item.value}
                value={item.value}
                className="grid cursor-pointer grid-cols-[16px_1fr] items-center gap-2 rounded-sm py-1.5 pr-3 pl-2 text-sm outline-hidden data-highlighted:bg-main data-selected:font-bold pointer-coarse:py-3"
              >
                <BaseSelect.ItemIndicator className="col-start-1">
                  <Check className="size-3.5" strokeWidth={3} />
                </BaseSelect.ItemIndicator>
                <BaseSelect.ItemText className="col-start-2">{item.label}</BaseSelect.ItemText>
              </BaseSelect.Item>
            ))}
          </BaseSelect.List>
        </BaseSelect.Popup>
      </BaseSelect.Positioner>
    </BaseSelect.Portal>
  </BaseSelect.Root>
);
