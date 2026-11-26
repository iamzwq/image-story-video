import { Field as BaseField } from "@base-ui/react/field";
import { Input as BaseInput } from "@base-ui/react/input";
import React from "react";
import { cn } from "../../lib/cn";

export const controlClass =
  "w-full min-w-0 rounded-base border-2 border-ink bg-white px-3 py-[7px] text-sm text-ink outline-none transition-shadow " +
  "placeholder:text-muted/60 focus:shadow-brutal-sm " +
  "disabled:cursor-not-allowed disabled:bg-paper disabled:text-muted";

/**
 * 表单项：标题 + 控件 + 说明。控件是 Input、Textarea、Select 时标题会自动关联到控件。
 * nativeLabel={false}：控件是按钮类（Select、Segmented），标题不用 <label>，免得点标题时触发按钮
 */
export const Field: React.FC<{
  label: React.ReactNode;
  hint?: React.ReactNode;
  nativeLabel?: boolean;
  className?: string;
  children: React.ReactNode;
}> = ({ label, hint, nativeLabel = true, className, children }) => (
  <BaseField.Root className={cn("flex min-w-0 flex-col gap-1.5", className)}>
    <BaseField.Label
      className="w-fit text-[13px] font-extrabold"
      {...(nativeLabel ? {} : { nativeLabel: false, render: <div /> })}
    >
      {label}
    </BaseField.Label>
    {children}
    {hint ? <BaseField.Description className="text-xs text-muted">{hint}</BaseField.Description> : null}
  </BaseField.Root>
);

export const Hint: React.FC<{ className?: string; children: React.ReactNode }> = ({ className, children }) => (
  <p className={cn("text-xs text-muted", className)}>{children}</p>
);

export const Input: React.FC<Omit<React.ComponentProps<typeof BaseInput>, "className"> & { className?: string }> = ({
  className,
  ...props
}) => <BaseInput className={cn(controlClass, className)} {...props} />;

type TextareaProps = Omit<React.ComponentProps<"textarea">, "ref">;

// Field.Control 换成 <textarea> 渲染，这样也能和 Field 的标题关联
export const Textarea: React.FC<TextareaProps> = ({ className, ...props }) => (
  <BaseField.Control
    render={<textarea />}
    className={cn(controlClass, "resize-y leading-relaxed", className)}
    {...(props as Omit<React.ComponentProps<typeof BaseField.Control>, "className">)}
  />
);
