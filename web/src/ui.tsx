import { ArrowRight, Volume2 } from "lucide-react";
import React, { useEffect, useRef, useState } from "react";
import type { EpisodeSummary, StoryboardOptions } from "./api";
import { isActive } from "./api";
import { Badge, Button, Field, Hint, Input, Segmented, Select, Spinner } from "./components/ui";
import { cn } from "./lib/cn";
import { ASPECTS, RATES, rateLabel, STAGES, VOICES } from "./constants";

/** 「去设置 →」链接 */
export const SettingsLink: React.FC<{ onClick?: () => void }> = ({ onClick }) => (
  <a href="#/settings" onClick={onClick} className="inline-flex items-center gap-0.5 whitespace-nowrap">
    去设置
    <ArrowRight className="size-3.5" strokeWidth={2.5} />
  </a>
);

export const StageBadge: React.FC<{ episode: EpisodeSummary }> = ({ episode }) => {
  if (isActive(episode.job)) {
    return (
      <Badge tone="info">
        <Spinner />
        {episode.job?.status === "queued" ? "排队中" : episode.job?.title}
      </Badge>
    );
  }
  const stage = STAGES[episode.stage];
  const { need, have } = episode.imageCount;
  return (
    <Badge tone={stage.tone}>
      {stage.label}
      {episode.stage === "images" ? ` ${have}/${need}` : ""}
    </Badge>
  );
};

/** 配音音色、语速，带试听。compact：放在窄栏或弹窗里时音色单独占一行 */
export const VoicePicker: React.FC<{
  voice: string;
  rate: string;
  disabled?: boolean;
  compact?: boolean;
  onChange: (voice: string, rate: string) => void;
}> = ({ voice, rate, disabled, compact, onChange }) => {
  const [state, setState] = useState<"idle" | "loading" | "playing">("idle");
  const [error, setError] = useState("");
  const audio = useRef<HTMLAudioElement | null>(null);
  useEffect(() => () => audio.current?.pause(), []);

  const play = () => {
    audio.current?.pause();
    setError("");
    setState("loading");
    const a = new Audio(`/api/voice-sample?voice=${encodeURIComponent(voice)}&rate=${encodeURIComponent(rate)}`);
    audio.current = a;
    a.onplaying = () => setState("playing");
    a.onended = () => setState("idle");
    a.onerror = () => {
      setState("idle");
      setError("试听失败：配音服务需要联网，稍后再试");
    };
    a.play().catch(() => undefined);
  };

  const voices = VOICES.map((v) => ({ value: v.id, label: `${v.name}：${v.note}` }));
  if (!VOICES.some((v) => v.id === voice)) {
    voices.push({ value: voice, label: voice });
  }
  const rates = RATES.map((r) => ({ value: r, label: rateLabel(r) }));
  if (!RATES.includes(rate)) {
    rates.push({ value: rate, label: rate });
  }

  return (
    <div
      className={cn(
        "grid items-end gap-2.5",
        compact
          ? "grid-cols-[minmax(0,1fr)_auto] [&>:first-child]:col-span-full"
          : "grid-cols-[minmax(0,1fr)_auto] md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_auto] max-md:[&>:first-child]:col-span-full",
      )}
    >
      <Field label="配音音色" nativeLabel={false}>
        <Select value={voice} items={voices} disabled={disabled} onChange={(v) => onChange(v, rate)} />
      </Field>
      <Field label="语速" nativeLabel={false}>
        <Select value={rate} items={rates} disabled={disabled} onChange={(r) => onChange(voice, r)} />
      </Field>
      <Button onClick={play} disabled={state !== "idle"} className="h-11">
        {state === "idle" ? <Volume2 /> : <Spinner />}
        {state === "loading" ? "生成试听…" : state === "playing" ? "播放中…" : "试听"}
      </Button>
      {error ? <span className="col-span-full text-xs text-danger-ink">{error}</span> : null}
    </div>
  );
};

/** 新写分镜时的选项：音色、语速、画面比例、图片张数 */
export const StoryboardOptionsForm: React.FC<{
  value: StoryboardOptions;
  disabled?: boolean;
  compact?: boolean;
  onChange: (value: StoryboardOptions) => void;
}> = ({ value, disabled, compact, onChange }) => (
  <div className="flex flex-col gap-4">
    <VoicePicker
      voice={value.voice}
      rate={value.rate}
      disabled={disabled}
      compact={compact}
      onChange={(voice, rate) => onChange({ ...value, voice, rate })}
    />
    <Field label="画面比例" nativeLabel={false}>
      <Segmented
        label="画面比例"
        value={value.aspect}
        disabled={disabled}
        options={ASPECTS.map((a) => ({ value: a.id, label: a.label, title: a.note }))}
        onChange={(aspect) => onChange({ ...value, aspect })}
      />
    </Field>
    <div className="flex flex-col gap-1.5">
      <span className="text-label font-extrabold">图片张数</span>
      <div className="flex flex-wrap items-center gap-2.5">
        <Segmented
          label="图片张数"
          value={value.images === null ? "auto" : "fixed"}
          disabled={disabled}
          options={[
            { value: "auto", label: "自动（每 5–10 秒一张）" },
            { value: "fixed", label: "指定张数" },
          ]}
          onChange={(mode) => onChange({ ...value, images: mode === "auto" ? null : (value.images ?? 20) })}
        />
        {value.images !== null ? (
          <Input
            aria-label="图片张数"
            className="w-24"
            type="number"
            min={1}
            max={500}
            value={value.images}
            disabled={disabled}
            onChange={(e) => onChange({ ...value, images: Math.max(1, Number(e.target.value) || 1) })}
          />
        ) : null}
      </div>
      <Hint>指定张数可以省钱，每张图对应一段较长的台词；开场和每一章至少 1 张，7 分钟的视频建议不少于 15 张</Hint>
    </div>
  </div>
);

/** 出图费用上限输入框，单位元 */
export const CostLimit: React.FC<{
  value: number;
  onChange: (value: number) => void;
  label: string;
  note?: React.ReactNode;
}> = ({ value, onChange, label, note }) => (
  <label className="flex flex-wrap items-center gap-2 font-semibold">
    {label}
    <Input
      className="w-20"
      type="number"
      min={1}
      value={value}
      onChange={(e) => onChange(Math.max(1, Number(e.target.value) || 1))}
    />
    元{note ? <span className="font-normal text-muted">{note}</span> : null}
  </label>
);
