import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// 让 tailwind-merge 认识 styles.css 里自定义的投影、圆角和字号，否则会把 shadow-brutal、text-label 当成颜色
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      shadow: ["brutal-sm", "brutal", "brutal-lg"],
      radius: ["base"],
      text: ["caption", "label", "reading"],
    },
  },
});

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));
