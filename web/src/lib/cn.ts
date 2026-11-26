import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// 让 tailwind-merge 认识 styles.css 里自定义的投影和圆角，否则会把 shadow-brutal 当成颜色
const twMerge = extendTailwindMerge({
  extend: { theme: { shadow: ["brutal-sm", "brutal", "brutal-lg"], radius: ["base"] } },
});

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));
