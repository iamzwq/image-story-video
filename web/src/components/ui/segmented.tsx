import { Toggle } from "@base-ui/react/toggle";
import { ToggleGroup } from "@base-ui/react/toggle-group";
import React from "react";
import { cn } from "../../lib/cn";

export type SegmentedOption<T extends string> = { value: T; label: React.ReactNode; title?: string };

/** 单选按钮组：选中的那一项填主色、带投影 */
export const Segmented = <T extends string>({
  value,
  options,
  onChange,
  disabled,
  size = "md",
  label,
}: {
  value: T;
  options: SegmentedOption<T>[];
  onChange: (value: T) => void;
  disabled?: boolean;
  size?: "md" | "sm";
  label?: string;
}) => (
  <ToggleGroup
    aria-label={label}
    value={[value]}
    disabled={disabled}
    onValueChange={(next) => {
      // 再点一次已选中的那一格不取消选择
      if (next.length) {
        onChange(next[0] as T);
      }
    }}
    className="flex max-w-full flex-wrap gap-2"
  >
    {options.map((o) => (
      <Toggle
        key={o.value}
        value={o.value}
        title={o.title}
        className={cn(
          "cursor-pointer rounded-base border-2 border-ink bg-white font-semibold whitespace-nowrap outline-hidden transition-[background-color,box-shadow,translate] duration-100",
          "hover:not-data-disabled:bg-main-soft focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ink",
          "data-pressed:-translate-x-px data-pressed:-translate-y-px data-pressed:bg-main data-pressed:font-extrabold data-pressed:shadow-brutal-sm data-pressed:hover:bg-main",
          "data-disabled:cursor-not-allowed data-disabled:opacity-55",
          size === "sm" ? "px-2.5 py-0.5 text-label pointer-coarse:min-h-11" : "px-3 py-1.5 text-sm pointer-coarse:min-h-13",
        )}
      >
        {o.label}
      </Toggle>
    ))}
  </ToggleGroup>
);
