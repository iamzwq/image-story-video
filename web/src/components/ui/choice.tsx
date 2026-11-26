import { Checkbox as BaseCheckbox } from "@base-ui/react/checkbox";
import { Radio as BaseRadio } from "@base-ui/react/radio";
import { RadioGroup as BaseRadioGroup } from "@base-ui/react/radio-group";
import { Check } from "lucide-react";
import React from "react";
import { cn } from "../../lib/cn";

export const Checkbox: React.FC<{
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
  children: React.ReactNode;
}> = ({ checked, onChange, disabled, className, children }) => (
  <label className={cn("flex w-fit cursor-pointer items-start gap-2.5", className)}>
    <BaseCheckbox.Root
      checked={checked}
      disabled={disabled}
      onCheckedChange={(c) => onChange(c)}
      className="mt-0.5 grid size-5 flex-none cursor-pointer place-items-center rounded-[4px] border-2 border-ink bg-white shadow-brutal-sm outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink data-checked:bg-main"
    >
      <BaseCheckbox.Indicator>
        <Check className="size-3.5" strokeWidth={3.5} />
      </BaseCheckbox.Indicator>
    </BaseCheckbox.Root>
    <span>{children}</span>
  </label>
);

export const RadioGroup: React.FC<{
  value: string;
  onChange: (value: string) => void;
  className?: string;
  children: React.ReactNode;
}> = ({ value, onChange, className, children }) => (
  <BaseRadioGroup value={value} onValueChange={(v) => onChange(v as string)} className={className}>
    {children}
  </BaseRadioGroup>
);

export const Radio: React.FC<{ value: string; className?: string; children: React.ReactNode }> = ({
  value,
  className,
  children,
}) => (
  <label className={cn("flex cursor-pointer items-center gap-2", className)}>
    <BaseRadio.Root
      value={value}
      className="grid size-5 flex-none cursor-pointer place-items-center rounded-full border-2 border-ink bg-white outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink data-checked:bg-main"
    >
      <BaseRadio.Indicator className="size-2 rounded-full bg-ink" />
    </BaseRadio.Root>
    {children}
  </label>
);
