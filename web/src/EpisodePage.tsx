import {
  ArrowRight,
  AudioLines,
  Brush,
  Captions,
  Check,
  Clapperboard,
  Download,
  FileText,
  FolderOpen,
  ImageDown,
  ImagePlus,
  Palette,
  Pencil,
  Play,
  RefreshCw,
  Save,
  Sparkles,
  Undo2,
  Zap,
} from "lucide-react";
import React, { Suspense, useCallback, useEffect, useRef, useState } from "react";
import type { EpisodeDetail, Estimate, Ready, Storyboard, StoryboardOptions } from "./api";
import { errorCode, errorText, formatDuration, formatSize, formatTime, isActive, request } from "./api";
import {
  Alert,
  Badge,
  Button,
  buttonClass,
  Card,
  CardTitle,
  Checkbox,
  Dialog,
  Disclosure,
  Field,
  Hint,
  Input,
  Lightbox,
  Page,
  PageHeader,
  Spinner,
  Textarea,
} from "./components/ui";
import type { Tone } from "./components/ui";
import { DEFAULT_OPTIONS } from "./constants";
import { takeFlash, useInterval, useLeaveGuard } from "./hooks";
import { JobPanel } from "./JobPanel";
import { cn } from "./lib/cn";
import { SceneList, StoryboardSettings } from "./Storyboard";
import { CostLimit, SettingsLink, StoryboardOptionsForm } from "./ui";

const Preview = React.lazy(() => import("./Preview").then((m) => ({ default: m.Preview })));

type Notice = { tone: "ok" | "warn" | "error"; text: string; code?: string };
type ImagesRequest = { mode: "pilot" | "missing" | "all" | "only"; ids?: string; title: string };
type DialogState =
  | { kind: "images"; request: ImagesRequest }
  | { kind: "confirm"; title: string; body: React.ReactNode; action: string; run: () => void }
  | { kind: "make" }
  | { kind: "rewrite" }
  | { kind: "zoom"; url: string };

const STEPS = ["文案", "分镜", "出图", "导出"];
const STEP_INDEX = { script: 1, draft: 1, images: 2, ready: 3, done: 4 };

const scriptTitles = (name: string) => {
  const [title, subtitle = ""] = name
    .replace(/\.md$/i, "")
    .replace(/^\d+[.\s_-]*/, "")
    .split("——");
  return { title: title.trim(), subtitle: subtitle.trim() };
};

const downloadUrl = (url: string, name: string) => `${url}&download=${encodeURIComponent(name)}`;

/** 「下一步」卡片：角标 + 标题 + 说明 + 操作。tone 为 ok 时角标带对勾 */
const StepCard: React.FC<{ tag: string; tone?: Tone; title: string; children: React.ReactNode }> = ({
  tag,
  tone = "accent",
  title,
  children,
}) => (
  <Card className="flex flex-col gap-3">
    <div className="flex flex-wrap items-center gap-2.5">
      <Badge tone={tone} className="px-2.5 py-0.5 text-[13px] [&_svg]:size-3.5">
        {tone === "ok" ? <Check strokeWidth={3} /> : <ArrowRight strokeWidth={3} />}
        {tag}
      </Badge>
      <h2 className="text-xl">{title}</h2>
    </div>
    {children}
  </Card>
);

const Actions: React.FC<{ className?: string; children: React.ReactNode }> = ({ className, children }) => (
  <div className={cn("flex flex-wrap items-center gap-3", className)}>{children}</div>
);

export const EpisodePage: React.FC<{ id: string; ready: Ready | null; onChanged: () => void }> = ({
  id,
  ready,
  onChanged,
}) => {
  const [detail, setDetail] = useState<EpisodeDetail | null>(null);
  const [loadError, setLoadError] = useState("");
  const [draft, setDraft] = useState<Storyboard | null>(null);
  const [dirty, setDirty] = useState(false);
  const dirtyRef = useRef(false);
  const [scriptDirty, setScriptDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(() => {
    const flash = takeFlash();
    return flash ? { tone: "warn", text: flash } : null;
  });
  const [dialog, setDialog] = useState<DialogState | null>(null);
  // 没在这一页改过选项时，用这一集记下的选项（新建视频时选的，或者上次写分镜用的）
  const [editedOptions, setOptions] = useState<StoryboardOptions | null>(null);

  const markDirty = (value: boolean) => {
    dirtyRef.current = value;
    setDirty(value);
  };

  const load = useCallback(async () => {
    try {
      const d = await request<EpisodeDetail>(`/api/episodes/${id}`);
      setDetail(d);
      setLoadError("");
      if (!dirtyRef.current) {
        setDraft(d.storyboard ? structuredClone(d.storyboard) : null);
      }
    } catch (e) {
      setLoadError(errorText(e));
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);
  const busy = isActive(detail?.job);
  // 任务运行时定时刷新，出图时新画好的图会陆续显示出来
  useInterval(load, busy ? 4000 : null);
  useEffect(() => {
    window.addEventListener("focus", load);
    return () => window.removeEventListener("focus", load);
  }, [load]);
  useLeaveGuard(dirty || scriptDirty);

  if (!detail) {
    return (
      <Page>
        {loadError ? (
          <Alert tone="error">
            {loadError} <a href="#/">回首页</a>
          </Alert>
        ) : (
          <p className="text-muted">加载中…</p>
        )}
      </Page>
    );
  }

  const sb = draft;
  const saved = detail.storyboard;
  const locked = busy;
  const jobsBlocked = busy || dirty || scriptDirty;
  const { need, have } = detail.imageCount;
  const missing = need - have;
  const step = STEP_INDEX[detail.stage];
  const options = editedOptions ?? detail.options ?? DEFAULT_OPTIONS;

  const startJob = async (kind: string, opts: Record<string, unknown> = {}) => {
    setNotice(null);
    setDialog(null);
    try {
      await request(`/api/episodes/${id}/jobs`, "POST", { kind, options: opts });
      await load();
      onChanged();
    } catch (e) {
      setNotice({ tone: "error", text: errorText(e), code: errorCode(e) });
    }
  };

  const savedOptions: StoryboardOptions = {
    voice: saved?.voice ?? options.voice,
    rate: saved?.rate ?? options.rate,
    aspect: saved?.aspect ?? options.aspect,
    images: options.images,
  };

  const openImages = (req: ImagesRequest) => setDialog({ kind: "images", request: req });

  const restyle = () =>
    setDialog({
      kind: "confirm",
      title: "AI 推荐画风",
      body: "大模型会按文案的题材、时代和基调推荐一个画风，只改画风，其他分镜内容不变。已有的图片要重画才会用上新画风。",
      action: "推荐画风",
      run: () => startJob("style"),
    });

  const render = () => {
    if (missing > 0) {
      setDialog({
        kind: "confirm",
        title: "导出视频",
        body: `还有 ${missing} 张图没有生成，导出的视频里先用相邻画面代替。确定现在导出吗？`,
        action: "导出",
        run: () => startJob("render"),
      });
    } else {
      startJob("render");
    }
  };

  const update = (fn: (s: Storyboard) => Storyboard) => {
    setDraft((s) => (s ? fn(s) : s));
    markDirty(true);
  };

  const save = async () => {
    if (!draft) {
      return;
    }
    setSaving(true);
    setNotice(null);
    try {
      await request(`/api/episodes/${id}/storyboard`, "PUT", { storyboard: draft });
      markDirty(false);
      await load();
      onChanged();
      setNotice({ tone: "ok", text: "已保存，正在更新配音和时间线（台词没改的话几秒就好）" });
    } catch (e) {
      setNotice({ tone: "error", text: errorText(e) });
    } finally {
      setSaving(false);
    }
  };

  const discard = () => {
    markDirty(false);
    setDraft(saved ? structuredClone(saved) : null);
  };

  const unsavedHint =
    dirty || scriptDirty ? <p className="font-semibold text-warn-ink">有未保存的修改，先保存再继续。</p> : null;

  // 导出过、但之后又改了内容：「下一步」卡片底部留一行，还能找到上次的成片
  const pastExport =
    detail.video && detail.stage !== "done" ? (
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-t-2 border-dashed border-ink/25 pt-3 text-[13px]">
        <span className="font-semibold text-muted">上次导出的成片（{formatTime(detail.video.mtime)}）：</span>
        <RevealButton episode={id} link />
        <DownloadLinks detail={detail} />
      </div>
    ) : null;

  const nextStep = () => {
    switch (detail.stage) {
      case "script":
        return (
          <StepCard tag="下一步" title="写分镜">
            <p>
              AI 会纠正容易读错的字、按内容推荐画风、设计反复出现的人物，再把文案分成一个个画面，写好每个画面的出图提示词。通常 1–3
              分钟，花费几分钱。
            </p>
            <div className="my-1">
              <StoryboardOptionsForm value={options} onChange={setOptions} disabled={locked} />
            </div>
            <Actions>
              <Button
                variant="primary"
                disabled={jobsBlocked || !detail.hasScript}
                onClick={() => startJob("storyboard", options)}
              >
                <Sparkles />
                AI 写分镜
              </Button>
              <Button disabled={jobsBlocked || !detail.hasScript} onClick={() => setDialog({ kind: "make" })}>
                <Zap />
                一键生成视频
              </Button>
              <Button variant="link" disabled={jobsBlocked || !detail.hasScript} onClick={() => startJob("draft", options)}>
                不用 AI，按配音时长自动分组
              </Button>
            </Actions>
            {unsavedHint}
            {ready && !ready.llm ? (
              <Alert tone="warn">
                还没有填写大模型设置，AI 写分镜之前先 <SettingsLink />
              </Alert>
            ) : null}
            {pastExport}
          </StepCard>
        );
      case "draft":
        return (
          <StepCard tag="下一步" title="补全分镜">
            <p>
              现在的分镜是按配音时长自动分组的草稿，还没有出图提示词{detail.hasStyle ? "" : "和画风"}
              。可以让 AI 写分镜（会覆盖草稿），也可以在下面逐个画面填写提示词{detail.hasStyle ? "" : "，并在「整体设置」里填写画风"}。
            </p>
            <Actions>
              <Button variant="primary" disabled={jobsBlocked} onClick={() => startJob("storyboard", savedOptions)}>
                <Sparkles />
                AI 写分镜
              </Button>
            </Actions>
            {unsavedHint}
            {pastExport}
          </StepCard>
        );
      case "images":
        return (
          <StepCard tag="下一步" title="出图">
            <p>
              {have ? `已有 ${have}/${need} 张图。` : `一共要画 ${need} 张图。`}
              {have === 0 && need > 4 ? "建议先试画 4 张看看画风和人物，满意再生成全部。" : ""}
              不满意的图，改好画风或提示词后点画面上的「重画」。
            </p>
            {!detail.hasStyle ? (
              <Alert tone="warn">
                还没有画风，出图前先
                <Button variant="link" disabled={jobsBlocked} onClick={() => startJob("style")}>
                  让 AI 推荐画风
                </Button>
                ，或者在下面的「整体设置」里自己填写。
              </Alert>
            ) : null}
            {ready && !ready.image ? (
              <Alert tone="warn">
                {ready.imageError} <SettingsLink />
              </Alert>
            ) : null}
            <Actions>
              {have === 0 && need > 4 ? (
                <Button
                  variant="primary"
                  disabled={jobsBlocked}
                  onClick={() => openImages({ mode: "pilot", title: "试画 4 张" })}
                >
                  <Brush />
                  试画 4 张
                </Button>
              ) : null}
              <Button
                variant={have ? "primary" : "default"}
                disabled={jobsBlocked}
                onClick={() =>
                  openImages({ mode: "missing", title: have ? `生成缺少的 ${missing} 张图` : `生成全部 ${need} 张图` })
                }
              >
                <ImagePlus />
                {have ? `生成缺少的 ${missing} 张` : `生成全部 ${need} 张`}
              </Button>
              {have ? (
                <Button variant="link" disabled={jobsBlocked} onClick={render}>
                  先导出看看（缺的图用相邻画面代替）
                </Button>
              ) : null}
            </Actions>
            {unsavedHint}
            {pastExport}
          </StepCard>
        );
      case "ready":
        return (
          <StepCard tag="下一步" title="导出视频">
            <p>
              {detail.video?.stale
                ? "导出之后又改过分镜或图片，重新导出才会更新成片。"
                : "图片都齐了。先在右边预览一遍，满意后导出 MP4 和封面。"}
              {detail.duration ? ` 视频时长 ${formatDuration(detail.duration)}，导出大约要几分钟。` : ""}
            </p>
            <Actions>
              <Button variant="primary" disabled={jobsBlocked} onClick={render}>
                <Clapperboard />
                {detail.video ? "重新导出视频" : "导出视频"}
              </Button>
            </Actions>
            {unsavedHint}
            {pastExport}
          </StepCard>
        );
      case "done": {
        const { video, cover } = detail;
        return (
          <StepCard tag="已完成" tone="ok" title="成片和封面都已导出">
            <div className="flex flex-wrap items-start gap-4">
              {cover ? (
                <button
                  type="button"
                  className="w-24 flex-none cursor-zoom-in overflow-hidden rounded-base border-2 border-ink shadow-brutal-sm"
                  title="看大图"
                  onClick={() => setDialog({ kind: "zoom", url: cover.url })}
                >
                  <img src={cover.url} alt="封面" className="block w-full" />
                </button>
              ) : null}
              <div className="flex min-w-0 flex-1 flex-col gap-3">
                <p>
                  之后修改了分镜或图片，再导出一次就行。
                  {video ? (
                    <span className="mt-1 block text-[13px] text-muted">
                      {formatSize(video.size)} · 导出于 {formatTime(video.mtime)}
                    </span>
                  ) : null}
                </p>
                <Actions>
                  {video ? <RevealButton episode={id} /> : null}
                  <Button disabled={jobsBlocked} onClick={render}>
                    <RefreshCw />
                    重新导出
                  </Button>
                </Actions>
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]">
                  <DownloadLinks detail={detail} />
                </div>
              </div>
            </div>
          </StepCard>
        );
      }
    }
  };

  return (
    <Page>
      <PageHeader
        eyebrow={
          <>
            第 {id} 集{detail.duration ? ` · ${formatDuration(detail.duration)}` : ""}
            {need ? ` · ${need} 个画面` : ""}
          </>
        }
        title={detail.title}
        subtitle={detail.subtitle || undefined}
        aside={
          <ol className="flex flex-wrap gap-1.5">
            {STEPS.map((name, i) => (
              <li
                key={name}
                className={cn(
                  "flex items-center gap-1.5 rounded-full border-2 border-ink py-1 pr-3 pl-1 text-[13px] font-bold",
                  i < step ? "bg-ok" : i === step ? "bg-main shadow-brutal-sm" : "bg-white text-muted",
                )}
              >
                <span className="grid size-5 place-items-center rounded-full border-2 border-ink bg-white text-[11px] font-black text-ink">
                  {i < step ? <Check className="size-3" strokeWidth={4} /> : i + 1}
                </span>
                {name}
              </li>
            ))}
          </ol>
        }
      />

      {notice ? (
        <Alert tone={notice.tone} onClose={() => setNotice(null)}>
          {notice.text}
          {notice.code === "settings" ? (
            <>
              {" "}
              <SettingsLink />
            </>
          ) : null}
        </Alert>
      ) : null}
      {detail.storyboardError ? (
        <Alert tone="error">
          分镜文件有问题：{detail.storyboardError}。可以修好 public/episodes/{id}/storyboard.json，或者按文案重写分镜。
        </Alert>
      ) : null}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_clamp(290px,28vw,400px)]">
        <div className="flex min-w-0 flex-col gap-5">
          {nextStep()}
          {saved ? (
            <div className="-mt-1 flex flex-wrap items-center gap-x-1 gap-y-0.5 text-[13px]">
              <span className="mr-1 font-semibold text-muted">更多操作：</span>
              <Button variant="link" disabled={jobsBlocked} onClick={() => setDialog({ kind: "rewrite" })}>
                <Sparkles />
                AI 重写分镜
              </Button>
              <Button variant="link" disabled={jobsBlocked} onClick={restyle}>
                <Palette />
                AI 重新推荐画风
              </Button>
              {have ? (
                <Button variant="link" disabled={jobsBlocked} onClick={() => openImages({ mode: "all", title: "全部重画" })}>
                  <RefreshCw />
                  全部重画
                </Button>
              ) : null}
              <Button variant="link" disabled={jobsBlocked} onClick={() => startJob("voice")}>
                <AudioLines />
                重新生成配音和时间线
              </Button>
              <Button variant="link" disabled={jobsBlocked} onClick={() => setDialog({ kind: "make" })}>
                <Zap />
                一键做完剩下的步骤
              </Button>
            </div>
          ) : null}
          {!saved ? (
            <ScriptCard
              key={detail.script?.text ?? ""}
              detail={detail}
              locked={locked}
              startOpen
              onDirty={setScriptDirty}
              onSaved={setDetail}
            />
          ) : null}
          {sb && saved ? (
            <>
              <StoryboardSettings
                sb={sb}
                castImages={detail.castImages}
                locked={locked}
                defaultOpen={have === 0}
                onUpdate={update}
                onRestyle={restyle}
                onZoom={(url) => setDialog({ kind: "zoom", url })}
              />
              <SceneList
                detail={detail}
                sb={sb}
                locked={locked}
                jobsBlocked={jobsBlocked}
                onUpdate={update}
                onRedraw={(sceneId) => openImages({ mode: "only", ids: sceneId, title: `重画 ${sceneId}` })}
                onZoom={(url) => setDialog({ kind: "zoom", url })}
              />
              <ScriptCard
                key={detail.script?.text ?? ""}
                detail={detail}
                locked={locked}
                startOpen={false}
                onDirty={setScriptDirty}
                onSaved={(d) => {
                  setDetail(d);
                  setNotice({ tone: "ok", text: "文案已保存。分镜还是按原来的文案写的，要按新文案重写，点「AI 重写分镜」。" });
                }}
              />
            </>
          ) : null}
        </div>

        {/* 单栏时任务进度和预览放在最上面，不用滚到底才看得到；右侧留出投影的位置 */}
        <aside className="flex flex-col gap-5 max-lg:order-first lg:sticky lg:top-4 lg:max-h-[calc(100vh-32px)] lg:overflow-y-auto lg:pr-2 lg:pb-2">
          {detail.job ? (
            <JobPanel
              key={detail.job.id}
              job={detail.job}
              onFinished={() => {
                load();
                onChanged();
              }}
            />
          ) : null}
          <Card className="flex flex-col gap-3 p-4">
            <CardTitle className="mb-0"><Play />预览</CardTitle>
            {detail.timeline && detail.timelineVersion ? (
              <Suspense fallback={<p className="text-muted">加载播放器…</p>}>
                <Preview episode={id} timeline={detail.timeline} version={detail.timelineVersion} />
              </Suspense>
            ) : (
              <p className="text-muted">写好分镜后可以在这里预览，还没出图的画面先显示占位图。</p>
            )}
            {dirty ? <Hint>预览的是保存前的版本，保存后会自动更新。</Hint> : null}
          </Card>
        </aside>
      </div>

      {dirty ? (
        <div className="fixed right-0 bottom-0 left-0 z-20 flex flex-wrap items-center gap-3 border-t-2 border-ink bg-main px-4 py-3 md:left-[248px] md:px-8">
          <span className="font-semibold">有未保存的修改。保存后会更新配音和时间线（改了台词、读音或音色才会重新配音）。</span>
          <span className="flex-1" />
          <Button disabled={saving} onClick={discard}>
            <Undo2 />
            放弃修改
          </Button>
          <Button variant="dark" disabled={saving || locked} onClick={save}>
            {saving ? <Spinner /> : <Save />}
            {saving ? "保存中…" : "保存修改"}
          </Button>
        </div>
      ) : null}

      {dialog?.kind === "images" ? (
        <ImagesDialog
          episode={id}
          req={dialog.request}
          onClose={() => setDialog(null)}
          onStart={(opts) => startJob("images", opts)}
        />
      ) : null}
      {dialog?.kind === "confirm" ? (
        <Dialog
          title={dialog.title}
          onClose={() => setDialog(null)}
          actions={
            <>
              <Button onClick={() => setDialog(null)}>取消</Button>
              <Button variant="primary" onClick={dialog.run}>
                {dialog.action}
              </Button>
            </>
          }
        >
          <p>{dialog.body}</p>
        </Dialog>
      ) : null}
      {dialog?.kind === "make" ? (
        <MakeDialog
          hasStoryboard={Boolean(saved)}
          onClose={() => setDialog(null)}
          onStart={(opts) => startJob("make", { ...options, ...opts })}
        />
      ) : null}
      {dialog?.kind === "rewrite" ? (
        <RewriteDialog
          initial={savedOptions}
          onClose={() => setDialog(null)}
          onStart={(opts) => startJob("storyboard", opts)}
        />
      ) : null}
      {dialog?.kind === "zoom" ? <Lightbox url={dialog.url} onClose={() => setDialog(null)} /> : null}
    </Page>
  );
};

const ScriptCard: React.FC<{
  detail: EpisodeDetail;
  locked: boolean;
  startOpen: boolean;
  onDirty: (dirty: boolean) => void;
  onSaved: (detail: EpisodeDetail) => void;
}> = ({ detail, locked, startOpen, onDirty, onSaved }) => {
  const original = detail.script ? scriptTitles(detail.script.name) : { title: detail.title, subtitle: detail.subtitle };
  const originalText = detail.script?.text ?? "";
  const [editing, setEditing] = useState(startOpen);
  const [title, setTitle] = useState(original.title);
  const [subtitle, setSubtitle] = useState(original.subtitle);
  const [text, setText] = useState(originalText);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const changed = text !== originalText || title !== original.title || subtitle !== original.subtitle;
  useEffect(() => {
    onDirty(changed);
  }, [changed, onDirty]);
  useEffect(() => () => onDirty(false), [onDirty]);

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      onSaved(await request<EpisodeDetail>(`/api/episodes/${detail.id}/script`, "PUT", { title, subtitle, text }));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  const form = (
    <div className="flex flex-col gap-3">
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="标题">
          <Input value={title} maxLength={60} disabled={locked} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label="副标题（可不填）">
          <Input value={subtitle} maxLength={60} disabled={locked} onChange={(e) => setSubtitle(e.target.value)} />
        </Field>
      </div>
      <Field label="文案">
        <Textarea
          className="min-h-[300px] text-[15px] leading-[1.8]"
          rows={16}
          value={text}
          disabled={locked}
          onChange={(e) => setText(e.target.value)}
        />
      </Field>
      <Actions>
        <Button variant="primary" disabled={!changed || saving || locked} onClick={save}>
          {saving ? <Spinner /> : <Save />}
          {saving ? "保存中…" : "保存文案"}
        </Button>
        {changed ? (
          <Button
            disabled={saving}
            onClick={() => {
              setTitle(original.title);
              setSubtitle(original.subtitle);
              setText(originalText);
            }}
          >
            <Undo2 />
            放弃修改
          </Button>
        ) : null}
        {error ? <span className="text-danger-ink">{error}</span> : null}
      </Actions>
    </div>
  );

  if (startOpen) {
    return (
      <Card>
        <CardTitle><FileText />文案</CardTitle>
        {detail.script ? form : <Alert tone="warn">找不到这一集的文案文件（texts/{detail.id}.标题.md）。</Alert>}
      </Card>
    );
  }
  return (
    <Card>
      <Disclosure title="文案" meta={detail.script?.name ?? "没有找到文案文件"}>
        <div className="flex flex-col gap-3">
          <Hint>
            分镜写好后，视频内容以分镜为准：只改个别台词，直接在上面的画面里改。想按改过的文案整个重写，先在这里改好文案，再点「AI 重写分镜」。
          </Hint>
          {editing ? (
            form
          ) : (
            <>
              <pre className="max-h-[360px] overflow-y-auto rounded-base border-2 border-ink bg-paper p-3 font-sans text-sm leading-[1.8]">
                {originalText}
              </pre>
              <div>
                <Button size="sm" disabled={locked || !detail.script} onClick={() => setEditing(true)}>
                  <Pencil />
                  修改文案
                </Button>
              </div>
            </>
          )}
        </div>
      </Disclosure>
    </Card>
  );
};

/** 下载成片、封面和字幕的文字链接 */
const DownloadLinks: React.FC<{ detail: EpisodeDetail }> = ({ detail }) => {
  const { video, cover } = detail;
  if (!video) {
    return null;
  }
  return (
    <>
      <a className={buttonClass({ variant: "link" })} href={downloadUrl(video.url, `${detail.title}.mp4`)}>
        <Download />
        下载视频
      </a>
      {cover ? (
        <a className={buttonClass({ variant: "link" })} href={downloadUrl(cover.url, `${detail.title}-封面.jpg`)}>
          <ImageDown />
          下载封面
        </a>
      ) : null}
      {detail.timeline ? (
        <a
          className={buttonClass({ variant: "link" })}
          href={`/episodes/${detail.id}/captions.srt?download=${encodeURIComponent(`${detail.title}.srt`)}`}
        >
          <Captions />
          字幕文件
        </a>
      ) : null}
    </>
  );
};

/** 在资源管理器里打开 out/ 并选中成片；浏览器打不开本地文件夹，所以交给后台去开 */
const RevealButton: React.FC<{ episode: string; link?: boolean }> = ({ episode, link }) => {
  const [error, setError] = useState("");
  const reveal = async () => {
    setError("");
    try {
      await request(`/api/episodes/${episode}/reveal`, "POST");
    } catch (e) {
      setError(errorText(e));
    }
  };
  return (
    <span className="inline-flex flex-col items-start gap-1.5">
      <Button variant={link ? "link" : "primary"} onClick={reveal}>
        <FolderOpen />
        打开所在文件夹
      </Button>
      {error ? <span className="text-xs text-danger-ink">{error}</span> : null}
    </span>
  );
};

const ImagesDialog: React.FC<{
  episode: string;
  req: ImagesRequest;
  onClose: () => void;
  onStart: (opts: Record<string, unknown>) => void;
}> = ({ episode, req, onClose, onStart }) => {
  const [noRefs, setNoRefs] = useState(false);
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [error, setError] = useState<{ text: string; code: string } | null>(null);
  const [maxCost, setMaxCost] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setEstimate(null);
    setError(null);
    const query = new URLSearchParams({ mode: req.mode });
    if (req.ids) {
      query.set("ids", req.ids);
    }
    if (req.mode === "pilot") {
      query.set("pilot", "4");
    }
    if (noRefs) {
      query.set("noRefs", "1");
    }
    request<Estimate>(`/api/episodes/${episode}/estimate?${query}`)
      .then((e) => {
        if (!cancelled) {
          setEstimate(e);
          setMaxCost((m) => m ?? Math.max(20, Math.ceil(e.cost * 1.5)));
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError({ text: errorText(e), code: errorCode(e) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [episode, req, noRefs]);

  return (
    <Dialog
      title={req.title}
      onClose={onClose}
      actions={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button
            variant="primary"
            disabled={!estimate || estimate.count === 0}
            onClick={() => onStart({ mode: req.mode, ids: req.ids, pilot: 4, noRefs, maxCost: maxCost ?? 20 })}
          >
            <ImagePlus />
            开始出图
          </Button>
        </>
      }
    >
      {error ? (
        <Alert tone="error">
          {error.text}
          {error.code === "settings" ? (
            <>
              {" "}
              <SettingsLink onClick={onClose} />
            </>
          ) : null}
        </Alert>
      ) : !estimate ? (
        <p className="text-muted">正在估算费用…</p>
      ) : estimate.count === 0 ? (
        <p>没有需要生成的图片：已有图片的分镜会跳过，要重画某一张，点那个画面上的「重画」。</p>
      ) : (
        <div className="flex flex-col gap-3.5">
          <p>
            用 <strong>{estimate.provider}</strong> 生成 {estimate.count} 张图（{estimate.ids.slice(0, 8).join("、")}
            {estimate.ids.length > 8 ? " 等" : ""}）
            {estimate.sheets.length ? `，先画 ${estimate.sheets.length} 张角色定妆图（${estimate.sheets.join("、")}）` : ""}
            {estimate.refs ? `，共带 ${estimate.refs} 张参考图` : ""}。
          </p>
          <div className="rounded-base border-2 border-ink bg-main-soft px-3.5 py-2.5">
            {estimate.priceKnown ? (
              <p>
                预计约{" "}
                <strong className="mx-0.5 inline-block rounded-[4px] bg-main px-1.5 text-2xl font-black">
                  {estimate.cost.toFixed(2)}
                </strong>{" "}
                元
              </p>
            ) : (
              <p className="font-semibold">这个模型不在内置价格表里，没法预估费用</p>
            )}
            <p className="text-xs text-muted">参考价，以平台账单为准；审核没通过或失败的不收费</p>
          </div>
          {estimate.refsSupported ? (
            <Checkbox checked={noRefs} onChange={setNoRefs}>
              不带参考图：省掉参考图的费用，人物前后一致性差一些
            </Checkbox>
          ) : null}
          <CostLimit
            label="费用上限"
            value={maxCost ?? 20}
            onChange={setMaxCost}
            note="（预计超过就不出图，不会花钱）"
          />
          <Hint>每张图通常 10–20 秒，同时画 2 张。被内容审核拦下的图，会让大模型改写提示词再试一次。</Hint>
        </div>
      )}
    </Dialog>
  );
};

const MakeDialog: React.FC<{
  hasStoryboard: boolean;
  onClose: () => void;
  onStart: (opts: Record<string, unknown>) => void;
}> = ({ hasStoryboard, onClose, onStart }) => {
  const [maxCost, setMaxCost] = useState(20);
  const [noRefs, setNoRefs] = useState(false);
  return (
    <Dialog
      title="一键生成视频"
      onClose={onClose}
      actions={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={() => onStart({ maxCost, noRefs })}>
            <Zap />
            开始
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3.5">
        <p>
          依次完成：{hasStoryboard ? "" : "AI 写分镜 → "}配音 → 生成缺少的图片 → 导出视频和封面，中途不需要操作
          {hasStoryboard ? "，已经做好的步骤会跳过" : ""}。
        </p>
        <CostLimit label="出图费用上限" value={maxCost} onChange={setMaxCost} note="（预计超过就不出图，不会花钱）" />
        <Checkbox checked={noRefs} onChange={setNoRefs}>
          不带参考图：省钱，人物前后一致性差一些
        </Checkbox>
        <Hint>5 分钟的视频大约要 15–30 分钟。没画成的图（通常是审核没过）先用相邻画面代替，结束后可以单独重画。</Hint>
      </div>
    </Dialog>
  );
};

const RewriteDialog: React.FC<{
  initial: StoryboardOptions;
  onClose: () => void;
  onStart: (opts: StoryboardOptions) => void;
}> = ({ initial, onClose, onStart }) => {
  const [opts, setOpts] = useState(initial);
  return (
    <Dialog
      title="AI 重写分镜"
      onClose={onClose}
      actions={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={() => onStart(opts)}>
            <Sparkles />
            重写分镜
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Alert tone="warn">
          会按文案从头写分镜：画风、角色表、读音和每个画面都会重写，网页上改过的内容会被覆盖（旧分镜备份为
          storyboard.bak.json）。分镜编号会重排，已有的图片可能对不上，需要重画。
        </Alert>
        <StoryboardOptionsForm value={opts} onChange={setOpts} compact />
      </div>
    </Dialog>
  );
};
