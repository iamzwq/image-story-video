import { Progress as BaseProgress } from "@base-ui/react/progress";
import React from "react";

/** value 为 null 时是不确定进度：一段色块来回滑动 */
export const Progress: React.FC<{ value: number | null; label?: string }> = ({ value, label }) => (
  <BaseProgress.Root value={value} aria-label={label}>
    <BaseProgress.Track className="relative h-4 overflow-hidden rounded-full border-2 border-ink bg-white">
      <BaseProgress.Indicator className="h-full border-r-2 border-ink bg-main bg-[repeating-linear-gradient(-45deg,transparent_0_6px,rgb(17_17_17/0.12)_6px_12px)] transition-[width] duration-500 data-indeterminate:w-1/3 data-indeterminate:animate-slide" />
    </BaseProgress.Track>
  </BaseProgress.Root>
);
