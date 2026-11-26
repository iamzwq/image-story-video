import React from "react";
import { cn } from "../../lib/cn";

export const Card: React.FC<React.ComponentProps<"section">> = ({ className, ...props }) => (
  <section className={cn("rounded-base border-2 border-ink bg-white p-5 shadow-brutal", className)} {...props} />
);

export const CardTitle: React.FC<React.ComponentProps<"h2">> = ({ className, ...props }) => (
  <h2 className={cn("mb-2.5 flex items-center gap-2 text-lg [&_svg]:size-5 [&_svg]:shrink-0", className)} {...props} />
);
