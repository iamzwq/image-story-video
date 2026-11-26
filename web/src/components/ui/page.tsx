import React from "react";
import { cn } from "../../lib/cn";

export const Page: React.FC<{ className?: string; children: React.ReactNode }> = ({ className, children }) => (
  <div className={cn("flex flex-col gap-5", className)}>{children}</div>
);

export const PageHeader: React.FC<{
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  eyebrow?: React.ReactNode;
  aside?: React.ReactNode;
}> = ({ title, subtitle, eyebrow, aside }) => (
  <header className="flex flex-wrap items-end justify-between gap-4">
    <div className="min-w-0">
      {eyebrow ? <div className="mb-1.5 text-[13px] font-semibold text-muted">{eyebrow}</div> : null}
      <h1 className="text-[28px] md:text-[32px]">{title}</h1>
      {subtitle ? <p className="mt-1.5 text-muted">{subtitle}</p> : null}
    </div>
    {aside}
  </header>
);
