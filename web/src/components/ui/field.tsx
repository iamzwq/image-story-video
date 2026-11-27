import { Field as BaseField } from "@base-ui/react/field";
import { Input as BaseInput } from "@base-ui/react/input";
import React from "react";
import { cn } from "../../lib/cn";

export const controlClass =
  "w-full min-w-0 rounded-base border-2 border-ink bg-white px-3 py-2 text-sm text-ink outline-hidden transition-shadow " +
  "placeholder:text-muted/85 focus:shadow-brutal-sm pointer-coarse:py-3 " +
  "disabled:cursor-not-allowed disabled:bg-paper disabled:text-muted";

/**
 * 表单项：标题 + 控件 + 说明。控件是 Input、Textarea、Select 时标题会自动关联到控件。
 * nativeLabel={false}：控件是按钮类（Select、Segmented），标题不用 <label>，免得点标题时触发按钮
 * hintInline：说明放在标题右边而不是控件下面，适合一句话的短说明；aside 放在标题行最右边（例如字数统计）
 */
export const Field: React.FC<{
  label: React.ReactNode;
  hint?: React.ReactNode;
  hintInline?: boolean;
  aside?: React.ReactNode;
  nativeLabel?: boolean;
  className?: string;
  children: React.ReactNode;
}> = ({ label, hint, hintInline, aside, nativeLabel = true, className, children }) => {
  const labelEl = (
    <BaseField.Label
      className="w-fit text-label font-extrabold"
      {...(nativeLabel ? {} : { nativeLabel: false, render: <div /> })}
    >
      {label}
    </BaseField.Label>
  );
  const inline = hint && hintInline;
  return (
    <BaseField.Root className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      {inline || aside ? (
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          {labelEl}
          {inline ? <BaseField.Description className="text-label text-muted">{hint}</BaseField.Description> : null}
          {aside ? <span className="ml-auto text-label font-semibold text-muted">{aside}</span> : null}
        </div>
      ) : (
        labelEl
      )}
      {children}
      {hint && !hintInline ? <BaseField.Description className="text-xs text-muted">{hint}</BaseField.Description> : null}
    </BaseField.Root>
  );
};

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
