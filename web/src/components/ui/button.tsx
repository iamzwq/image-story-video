import { Button as BaseButton } from "@base-ui/react/button";
import React from "react";
import { cn } from "../../lib/cn";

export type ButtonVariant = "primary" | "default" | "dark" | "link";
export type ButtonSize = "md" | "sm";

const base =
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap font-bold no-underline select-none cursor-pointer " +
  "[&_svg]:size-4 [&_svg]:shrink-0 " +
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink " +
  "data-disabled:cursor-not-allowed data-disabled:opacity-45";

// 硬投影按钮：悬停时往投影方向挪一半，按下时贴住（投影按像素给，位移也要用同样的像素值才对得齐）
const pressable =
  "rounded-base border-2 border-ink shadow-brutal transition-[translate,box-shadow] duration-100 motion-reduce:transition-none " +
  "hover:not-data-disabled:translate-x-[2px] hover:not-data-disabled:translate-y-[2px] hover:not-data-disabled:shadow-brutal-sm " +
  "active:not-data-disabled:translate-x-[4px] active:not-data-disabled:translate-y-[4px] active:not-data-disabled:shadow-none";

const variants: Record<ButtonVariant, string> = {
  primary: `${pressable} bg-main text-ink hover:bg-main`,
  default: `${pressable} bg-white text-ink hover:bg-white`,
  dark: `${pressable} bg-ink text-white hover:bg-ink`,
  link: "rounded-xs px-1 py-0.5 text-ink underline decoration-2 underline-offset-3 hover:not-data-disabled:bg-main pointer-coarse:min-h-11",
};

// 触屏上把按钮加高到 44px 左右，方便手指点
const sizes: Record<ButtonSize, string> = {
  md: "h-10 px-4 text-sm pointer-coarse:h-13",
  sm: "h-8 px-3 text-label pointer-coarse:h-11",
};

export const buttonClass = ({
  variant = "default",
  size = "md",
  block,
  className,
}: { variant?: ButtonVariant; size?: ButtonSize; block?: boolean; className?: string } = {}) =>
  cn(base, variants[variant], variant === "link" ? "" : sizes[size], block && "w-full", className);

export type ButtonProps = Omit<React.ComponentProps<typeof BaseButton>, "className"> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  block?: boolean;
  className?: string;
};

export const Button: React.FC<ButtonProps> = ({ variant, size, block, className, type = "button", ...props }) => (
  <BaseButton type={type} className={buttonClass({ variant, size, block, className })} {...props} />
);
