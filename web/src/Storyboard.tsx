import {
  BookOpen,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  ImageOff,
  ImagePlus,
  Link2,
  Pencil,
  Plus,
  RefreshCw,
  Sparkles,
  Trash,
  TriangleExclamationPoint,
  User,
  Video,
} from "lucide-react";
import React, { useEffect, useRef, useState } from "react";
import type { EpisodeDetail, Motion, Scene, SceneImage, Storyboard } from "./api";
import { Button, Card, Chip, Disclosure, Field, Hint, Input, Segmented, Select, Textarea } from "./components/ui";
import { MOTIONS } from "./constants";
import { cn } from "./lib/cn";
import { VoicePicker } from "./ui";

type Update = (fn: (sb: Storyboard) => Storyboard) => void;

const NO_ENTRIES: Record<string, string> = {};

export const StoryboardSettings: React.FC<{
  sb: Storyboard;
  castImages: Record<string, string>;
  locked: boolean;
  defaultOpen: boolean;
  onUpdate: Update;
  onRestyle: () => void;
  onZoom: (url: string) => void;
}> = ({ sb, castImages, locked, defaultOpen, onUpdate, onRestyle, onZoom }) => {
  const [open, setOpen] = useState(defaultOpen);
  const cast = sb.cast ?? NO_ENTRIES;
  return (
    <Card>
      <Disclosure title="整体设置" meta="画风、人物、读音、配音" open={open} onOpenChange={setOpen}>
        <div className="flex flex-col gap-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="标题">
              <Input
                value={sb.title ?? ""}
                disabled={locked}
                onChange={(e) => onUpdate((s) => ({ ...s, title: e.target.value }))}
              />
            </Field>
            <Field label="副标题">
              <Input
                value={sb.subtitle ?? ""}
                disabled={locked}
                onChange={(e) => onUpdate((s) => ({ ...s, subtitle: e.target.value }))}
              />
            </Field>
          </div>
          <Field
            label="画风"
            hint="会拼在每条出图提示词的末尾，让所有图片看起来是同一套作品。改了画风，已有的图片要重画才会用上新画风。"
          >
            <Textarea
              rows={4}
              value={sb.imageStyle ?? ""}
              disabled={locked}
              placeholder="例如：以绢帛为底，矿物颜料平涂，墨线勾形……（写怎么画，不写画什么）"
              onChange={(e) => onUpdate((s) => ({ ...s, imageStyle: e.target.value }))}
            />
          </Field>
          <div>
            <Button size="sm" disabled={locked} onClick={onRestyle}>
              <Sparkles />
              让 AI 按内容推荐画风
            </Button>
          </div>
          <div className="flex flex-col gap-1.5">
            <VoicePicker
              voice={sb.voice ?? "zh-CN-YunxiNeural"}
              rate={sb.rate ?? "+0%"}
              disabled={locked}
              onChange={(voice, rate) => onUpdate((s) => ({ ...s, voice, rate }))}
            />
            <Hint>改了音色或语速，保存后会重新配音（免费，句子多时要一两分钟）。</Hint>
          </div>
          <CastEditor
            cast={cast}
            images={castImages}
            locked={locked}
            onZoom={onZoom}
            onChange={(next) => onUpdate((s) => ({ ...s, cast: next }))}
          />
          <PronunciationEditor
            value={sb.pronunciation ?? NO_ENTRIES}
            locked={locked}
            onChange={(next) => onUpdate((s) => ({ ...s, pronunciation: next }))}
          />
          <p className="text-muted">
            画面比例：<strong className="text-ink">{sb.aspect ?? "9:16"}</strong>（换比例要重写分镜，图片也要全部重画）
          </p>
        </div>
      </Disclosure>
    </Card>
  );
};

const sectionLabel = "text-[13px] font-extrabold";

const CastEditor: React.FC<{
  cast: Record<string, string>;
  images: Record<string, string>;
  locked: boolean;
  onChange: (cast: Record<string, string>) => void;
  onZoom: (url: string) => void;
}> = ({ cast, images, locked, onChange, onZoom }) => {
  const names = Object.keys(cast);
  return (
    <div className="flex flex-col gap-1.5">
      <span className={sectionLabel}>角色表</span>
      {names.length ? (
        <>
          <Hint>
            出图时先给每个角色画一张定妆图，之后有这个角色的画面都参考它，让人物前后长得一样。外貌只写各个画面都不变的特征；改了外貌，下次出图会自动重画定妆图。
          </Hint>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-3">
            {names.map((name) => (
              <div key={name} className="flex gap-3 rounded-base border-2 border-ink bg-paper p-2.5">
                {images[name] ? (
                  <button
                    type="button"
                    className="aspect-3/4 w-18 flex-none cursor-zoom-in overflow-hidden rounded-[4px] border-2 border-ink bg-white"
                    onClick={() => onZoom(images[name])}
                  >
                    <img src={images[name]} alt={name} loading="lazy" className="size-full object-cover" />
                  </button>
                ) : (
                  <div className="grid aspect-3/4 w-18 flex-none place-items-center rounded-[4px] border-2 border-dashed border-ink bg-white p-1 text-center text-[11px] text-muted">
                    还没有定妆图
                  </div>
                )}
                <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                  <strong className="font-black">{name}</strong>
                  <Textarea
                    aria-label={`${name}的外貌`}
                    rows={3}
                    value={cast[name]}
                    disabled={locked}
                    onChange={(e) => onChange({ ...cast, [name]: e.target.value })}
                  />
                </div>
              </div>
            ))}
          </div>
        </>
      ) : (
        <Hint>这一集没有需要固定长相的人物。</Hint>
      )}
    </div>
  );
};

const PronunciationEditor: React.FC<{
  value: Record<string, string>;
  locked: boolean;
  onChange: (value: Record<string, string>) => void;
}> = ({ value, locked, onChange }) => {
  // 一边输入一边改对象的键会打乱顺序，所以编辑时用列表，只把填完整的行写回分镜
  const [rows, setRows] = useState<[string, string][]>(() => Object.entries(value));
  const emitted = useRef(value);
  useEffect(() => {
    if (value !== emitted.current) {
      emitted.current = value;
      setRows(Object.entries(value));
    }
  }, [value]);

  const commit = (next: [string, string][]) => {
    setRows(next);
    const obj = Object.fromEntries(
      next.filter(([w, s]) => w.trim() && s.trim()).map(([w, s]) => [w.trim(), s.trim()]),
    );
    emitted.current = obj;
    onChange(obj);
  };

  return (
    <div className="flex flex-col gap-1.5">
      <span className={sectionLabel}>读音纠正</span>
      <Hint>
        只影响配音，字幕仍显示原文。例如「单于」念「蝉于」、「221年」念「二百二十一年」。没填完整的行不会保存。
      </Hint>
      <div className="flex flex-col gap-2">
        {rows.map(([word, say], i) => {
          const incomplete = !(word.trim() && say.trim());
          return (
            <div
              key={i}
              className="grid max-w-140 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto] items-center gap-2"
            >
              <Input
                aria-label="原文"
                className={cn(incomplete && "border-dashed")}
                value={word}
                placeholder="原文"
                disabled={locked}
                onChange={(e) => commit(rows.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))}
              />
              <span className="font-semibold text-muted">念作</span>
              <Input
                aria-label="配音念的字"
                className={cn(incomplete && "border-dashed")}
                value={say}
                placeholder="配音念的字"
                disabled={locked}
                onChange={(e) => commit(rows.map((r, j) => (j === i ? [r[0], e.target.value] : r)))}
              />
              <Button
                size="sm"
                className="w-8 px-0"
                disabled={locked}
                aria-label="删除"
                onClick={() => commit(rows.filter((_, j) => j !== i))}
              >
                <Trash />
              </Button>
            </div>
          );
        })}
      </div>
      <div className="mt-1">
        <Button size="sm" disabled={locked} onClick={() => setRows([...rows, ["", ""]])}>
          <Plus strokeWidth={3} />
          添加一项
        </Button>
      </div>
    </div>
  );
};

type Filter = "all" | "missing" | "changed";

// 画面多时默认只显示前几个，点「展开全部」再显示其余的
const PREVIEW_SCENES = 3;

/** 前 limit 个画面（连同夹在中间的章节行）在列表里结束的位置 */
const cutAfter = (scenes: Scene[], limit: number) => {
  let count = 0;
  for (let i = 0; i < scenes.length; i++) {
    if (scenes[i].type !== "chapter" && ++count > limit) {
      return i;
    }
  }
  return scenes.length;
};

export const SceneList: React.FC<{
  detail: EpisodeDetail;
  sb: Storyboard;
  locked: boolean;
  jobsBlocked: boolean;
  onUpdate: Update;
  onRedraw: (id: string) => void;
  onZoom: (url: string) => void;
}> = ({ detail, sb, locked, jobsBlocked, onUpdate, onRedraw, onZoom }) => {
  const [filter, setFilter] = useState<Filter>("all");
  const [expanded, setExpanded] = useState(false);
  const sectionRef = useRef<HTMLElement>(null);
  const castNames = Object.keys(sb.cast ?? NO_ENTRIES);
  const aspect = (sb.aspect ?? "9:16").replace(":", " / ");
  const isMissing = (sc: Scene) => sc.type !== "chapter" && !sc.reuse && !detail.sceneImages[sc.id];
  const isChanged = (sc: Scene) => {
    const img = detail.sceneImages[sc.id];
    return Boolean(img && img.prompt !== null && img.prompt !== (sc.prompt ?? ""));
  };
  const missing = sb.scenes.filter(isMissing).length;
  const changed = sb.scenes.filter(isChanged).length;
  const shown = sb.scenes.filter((sc) =>
    filter === "missing" ? isMissing(sc) : filter === "changed" ? isChanged(sc) : true,
  );
  const imageCount = sb.scenes.filter((sc) => sc.type !== "chapter").length;
  const shownCount = shown.filter((sc) => sc.type !== "chapter").length;
  const foldable = shownCount > PREVIEW_SCENES;
  const visible = foldable && !expanded ? shown.slice(0, cutAfter(shown, PREVIEW_SCENES)) : shown;

  const collapse = () => {
    setExpanded(false);
    sectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const updateScene = (id: string, patch: Partial<Scene>) =>
    onUpdate((s) => ({ ...s, scenes: s.scenes.map((x) => (x.id === id ? { ...x, ...patch } : x)) }));

  return (
    <section ref={sectionRef} className="flex scroll-mt-4 flex-col gap-3">
      <div className="mt-1 flex flex-wrap items-center justify-between gap-2.5">
        <h2 className="text-xl">画面（{imageCount} 个）</h2>
        <Segmented
          label="筛选画面"
          size="sm"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: "全部" },
            { value: "missing", label: `缺图 ${missing}` },
            { value: "changed", label: `提示词改过 ${changed}` },
          ]}
        />
      </div>
      {locked ? <p className="text-muted">任务运行中，结束后才能修改分镜。</p> : null}
      {shown.length === 0 ? <p className="text-muted">没有符合条件的画面。</p> : null}
      {visible.map((sc) =>
        sc.type === "chapter" ? (
          <div
            key={sc.id}
            className="flex flex-wrap items-baseline gap-2.5 rounded-base border-2 border-ink bg-ink px-3.5 py-2.5 text-white"
          >
            <Chip>
              <BookOpen />
              章节
            </Chip>
            <strong className="font-black">{[sc.kicker, sc.title].filter(Boolean).join(" · ")}</strong>
            {sc.lines.length ? <span className="text-white/65">{sc.lines.join("")}</span> : null}
          </div>
        ) : (
          <SceneCard
            key={sc.id}
            scene={sc}
            image={detail.sceneImages[sc.id]}
            reuseImage={sc.reuse ? detail.sceneImages[sc.reuse] : undefined}
            duration={detail.durations[sc.id]}
            changed={isChanged(sc)}
            castNames={castNames}
            aspect={aspect}
            locked={locked}
            jobsBlocked={jobsBlocked}
            onChange={(patch) => updateScene(sc.id, patch)}
            onRedraw={() => onRedraw(sc.id)}
            onZoom={onZoom}
          />
        ),
      )}
      {foldable ? (
        expanded ? (
          <Button block onClick={collapse}>
            <ChevronUp strokeWidth={3} />
            收起，只看前 {PREVIEW_SCENES} 个
          </Button>
        ) : (
          <Button block onClick={() => setExpanded(true)}>
            <ChevronDown strokeWidth={3} />
            展开全部（还有 {shownCount - PREVIEW_SCENES} 个画面）
          </Button>
        )
      ) : null}
    </section>
  );
};

const SceneCard: React.FC<{
  scene: Scene;
  image?: SceneImage;
  reuseImage?: SceneImage;
  duration?: number;
  changed: boolean;
  castNames: string[];
  aspect: string;
  locked: boolean;
  jobsBlocked: boolean;
  onChange: (patch: Partial<Scene>) => void;
  onRedraw: () => void;
  onZoom: (url: string) => void;
}> = ({ scene, image, reuseImage, duration, changed, castNames, aspect, locked, jobsBlocked, onChange, onRedraw, onZoom }) => {
  const [editing, setEditing] = useState(false);
  const shown = image ?? reuseImage;
  const motion = MOTIONS.find((m) => m.id === scene.motion)?.label;
  return (
    <article
      className={cn(
        "grid grid-cols-[96px_minmax(0,1fr)] gap-4 rounded-base border-2 border-ink bg-white p-3 transition-shadow md:grid-cols-[132px_minmax(0,1fr)]",
        editing ? "shadow-brutal" : "shadow-brutal-sm",
      )}
    >
      <button
        type="button"
        className="max-h-59 cursor-zoom-in self-start overflow-hidden rounded-[4px] border-2 border-ink bg-[repeating-linear-gradient(135deg,#fdf8ec_0_10px,#f3ead2_10px_20px)] text-xs font-semibold text-muted disabled:cursor-default"
        style={{ aspectRatio: aspect }}
        disabled={!shown}
        onClick={() => shown && onZoom(shown.url)}
      >
        {shown ? (
          <img src={shown.url} alt={scene.visual || scene.id} loading="lazy" className="size-full object-cover" />
        ) : (
          <span className="flex flex-col items-center gap-1 px-1">
            {scene.reuse ? <Link2 className="size-5" /> : <ImageOff className="size-5" />}
            {scene.reuse ? `复用 ${scene.reuse}` : "待出图"}
          </span>
        )}
      </button>
      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex items-start gap-2">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1 pt-1">
            <span className="rounded-[4px] bg-ink px-1.5 font-mono text-xs leading-5 font-bold text-main">{scene.id}</span>
            <strong className="font-black">{scene.visual || "（没有画面说明）"}</strong>
            {duration !== undefined ? (
              <span className="inline-flex items-center gap-0.5 text-xs text-muted">
                <Clock className="size-3" />
                {duration} 秒
              </span>
            ) : null}
          </div>
          <div className="flex flex-none gap-2">
            <Button size="sm" variant={editing ? "dark" : "default"} disabled={locked} onClick={() => setEditing(!editing)}>
              {editing ? <ChevronUp strokeWidth={3} /> : <Pencil />}
              {editing ? "收起" : "编辑"}
            </Button>
            {scene.reuse ? null : (
              <Button
                size="sm"
                variant={image ? "default" : "primary"}
                disabled={jobsBlocked || !(scene.prompt ?? "").trim()}
                title={jobsBlocked ? "有未保存的修改或任务在运行" : undefined}
                onClick={onRedraw}
              >
                {image ? <RefreshCw /> : <ImagePlus />}
                {image ? "重画" : "出图"}
              </Button>
            )}
          </div>
        </div>
        {editing ? (
          <SceneEditor scene={scene} castNames={castNames} locked={locked} onChange={onChange} />
        ) : (
          <>
            <p className="text-[15px] leading-[1.75]">
              {scene.lines.join("") || <span className="text-muted">（没有台词，停留 {scene.hold ?? 2} 秒）</span>}
            </p>
            {scene.reuse ? (
              <p className="text-muted">复用 {scene.reuse} 的图片，不用单独出图</p>
            ) : (
              <p className="text-[13px] text-muted">
                {scene.prompt || <span className="font-semibold text-warn-ink">还没有出图提示词</span>}
              </p>
            )}
            <div className="flex flex-wrap gap-1.5">
              {(scene.cast ?? []).map((n) => (
                <Chip key={n}>
                  <User />
                  {n}
                </Chip>
              ))}
              {motion ? (
                <Chip tone="plain">
                  <Video />
                  镜头：{motion}
                </Chip>
              ) : null}
              {scene.follow ? (
                <Chip tone="plain">
                  <Link2 />
                  延续 {scene.follow} 的场景
                </Chip>
              ) : null}
              {changed ? (
                <Chip tone="warn">
                  <TriangleExclamationPoint />
                  提示词改过，重画后才会用上
                </Chip>
              ) : null}
            </div>
          </>
        )}
      </div>
    </article>
  );
};

const splitLines = (text: string) =>
  text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

const SceneEditor: React.FC<{
  scene: Scene;
  castNames: string[];
  locked: boolean;
  onChange: (patch: Partial<Scene>) => void;
}> = ({ scene, castNames, locked, onChange }) => {
  // 台词按行编辑：保留输入中的空行，写回分镜时去掉
  const joined = scene.lines.join("\n");
  const [linesText, setLinesText] = useState(joined);
  // 分镜被外面换掉了（放弃修改、任务结束后重新加载）时跟着更新；自己正在输入时不打断
  useEffect(() => {
    setLinesText((text) => (splitLines(text).join("\n") === joined ? text : joined));
  }, [joined]);
  const cast = scene.cast ?? [];
  return (
    <div className="flex flex-col gap-3 pt-1">
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="画面说明">
          <Input
            value={scene.visual ?? ""}
            maxLength={16}
            disabled={locked}
            onChange={(e) => onChange({ visual: e.target.value })}
          />
        </Field>
        <Field label="镜头运动" nativeLabel={false}>
          <Select
            value={scene.motion ?? ""}
            disabled={locked}
            items={[{ value: "", label: "自动" }, ...MOTIONS.map((m) => ({ value: m.id, label: m.label }))]}
            onChange={(v) => onChange({ motion: (v || undefined) as Motion | undefined })}
          />
        </Field>
      </div>
      <Field label="台词" hint="一行一句。改了台词，保存后会重新配音，字幕也跟着变。">
        <Textarea
          rows={Math.max(2, linesText.split("\n").length)}
          value={linesText}
          disabled={locked}
          onChange={(e) => {
            setLinesText(e.target.value);
            onChange({ lines: splitLines(e.target.value) });
          }}
        />
      </Field>
      {scene.reuse ? null : (
        <Field
          label="出图提示词"
          hint="只写画面内容：主体、动作、场景、景别、光线。画风和画面比例会自动加上；画面里不要出现文字。"
        >
          <Textarea
            rows={4}
            value={scene.prompt ?? ""}
            disabled={locked}
            onChange={(e) => onChange({ prompt: e.target.value })}
          />
        </Field>
      )}
      {castNames.length && !scene.reuse ? (
        <div className="flex flex-col gap-1.5">
          <span className={sectionLabel}>画面里的角色</span>
          <div className="flex flex-wrap gap-1.5">
            {castNames.map((n) => {
              const on = cast.includes(n);
              return (
                <button
                  key={n}
                  type="button"
                  aria-pressed={on}
                  className={cn(
                    "inline-flex cursor-pointer items-center gap-1 rounded-full border-2 border-ink px-2.5 text-xs leading-5 font-semibold disabled:cursor-not-allowed disabled:opacity-55",
                    on ? "bg-main shadow-brutal-sm" : "bg-white hover:bg-main-soft",
                  )}
                  disabled={locked}
                  onClick={() => {
                    const next = on ? cast.filter((x) => x !== n) : [...cast, n];
                    onChange({ cast: next.length ? next : undefined });
                  }}
                >
                  {on ? <Check className="size-3" strokeWidth={3.5} /> : <Plus className="size-3" strokeWidth={3} />}
                  {n}
                </button>
              );
            })}
          </div>
          <Hint>选中的角色出图时会参考他的定妆图；提示词里直接写角色名，不用再写长相。</Hint>
        </div>
      ) : null}
    </div>
  );
};
