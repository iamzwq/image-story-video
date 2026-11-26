import { Ban, Check, Clock, X } from "lucide-react";
import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Job, JobLog, JobStatus } from "./api";
import { errorText, formatElapsed, isActive, request, RequestError } from "./api";
import { Alert, Button, Card, Dialog, Disclosure, Progress, Spinner } from "./components/ui";
import { useInterval } from "./hooks";
import { cn } from "./lib/cn";

const STATUS_TEXT: Record<JobStatus, string> = {
  queued: "排队中",
  running: "运行中",
  done: "完成",
  failed: "没有成功",
  cancelled: "已取消",
};

const STATUS_ICON: Record<JobStatus, React.ReactNode> = {
  queued: <Clock />,
  running: <Spinner />,
  done: <Check strokeWidth={3} />,
  failed: <X strokeWidth={3} />,
  cancelled: <Ban strokeWidth={2.5} />,
};

const STATUS_COLOR: Record<JobStatus, string> = {
  queued: "bg-info",
  running: "bg-main",
  done: "bg-ok",
  failed: "bg-danger",
  cancelled: "bg-white",
};

// 日志里每条命令对应的步骤名
const COMMAND_LABELS: [RegExp, string][] = [
  [/gen_storyboard\.py .*--style/, "推荐画风"],
  [/gen_storyboard\.py/, "写分镜"],
  [/build_episode\.py/, "配音、字幕、时间线"],
  [/gen_images\.py/, "出图"],
  [/remotion render/, "导出视频"],
  [/make_cover\.py/, "生成封面"],
  [/make_video\.py/, "一键生成"],
];

/** 从日志里找出当前步骤和进度：脚本会打印「[3/40] …」「已合成 10/40」，Remotion 会打印「Rendered 120/3000」 */
const parseProgress = (lines: string[]) => {
  let stage = "";
  let progress: [number, number] | null = null;
  for (const raw of lines) {
    const line = raw.trim();
    if (line.startsWith("$ ")) {
      stage = COMMAND_LABELS.find(([re]) => re.test(line))?.[1] ?? "";
      progress = null;
      continue;
    }
    const header = /^=+ \[(\d+)\/(\d+)\] (.+?) =+$/.exec(line);
    if (header) {
      stage = `第 ${header[1]}/${header[2]} 步：${header[3]}`;
      progress = null;
      continue;
    }
    const m =
      /^\[(\d+)\/(\d+)\]/.exec(line) ??
      /已合成 (\d+)\/(\d+)/.exec(line) ??
      /(?:Rendered|Rendering|Encoded|Encoding|Stitched|Stitching)\D*?(\d+)\s*\/\s*(\d+)/i.exec(line);
    if (m) {
      progress = [Number(m[1]), Number(m[2])];
    }
  }
  return { stage, progress };
};

export const JobPanel: React.FC<{ job: Job; onFinished: () => void }> = ({ job, onFinished }) => {
  const [info, setInfo] = useState<Job>(job);
  const [lines, setLines] = useState<string[]>([]);
  const [lost, setLost] = useState(false);
  const [now, setNow] = useState(() => Date.now() / 1000);
  const [cancelError, setCancelError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [logOpen, setLogOpen] = useState(job.status === "failed");
  const finished = useRef(onFinished);
  const logRef = useRef<HTMLPreElement>(null);
  const stick = useRef(true);
  useEffect(() => {
    finished.current = onFinished;
  });

  // 父组件用 key={job.id} 换任务，所以这里只在挂载时开始轮询
  useEffect(() => {
    let stopped = false;
    let timer = 0;
    let offset = 0;
    let collected: string[] = [];
    let sawActive = isActive(job);
    const poll = async () => {
      try {
        const data = await request<JobLog>(`/api/jobs/${job.id}?offset=${offset}`);
        if (stopped) {
          return;
        }
        collected = data.truncated ? data.lines : collected.concat(data.lines);
        offset = data.offset;
        setInfo(data);
        setLines(collected);
        if (isActive(data)) {
          sawActive = true;
          timer = window.setTimeout(poll, 1000);
        } else if (sawActive) {
          finished.current();
        }
      } catch (e) {
        if (stopped) {
          return;
        }
        if (e instanceof RequestError && e.status === 404) {
          setLost(true);
          return;
        }
        timer = window.setTimeout(poll, 3000);
      }
    };
    poll();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const active = isActive(info);
  useInterval(() => setNow(Date.now() / 1000), active ? 1000 : null);
  const failed = info.status === "failed";
  // 失败时自动展开日志
  useEffect(() => {
    if (failed) {
      setLogOpen(true);
    }
  }, [failed]);

  useLayoutEffect(() => {
    const el = logRef.current;
    if (el && stick.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [lines, logOpen]);

  const cancel = async () => {
    setConfirming(false);
    try {
      setInfo(await request<Job>(`/api/jobs/${info.id}/cancel`, "POST"));
    } catch (e) {
      setCancelError(errorText(e));
    }
  };

  const { stage, progress } = parseProgress(lines);
  const last = [...lines].reverse().find((l) => l.trim() && !l.startsWith("$ "))?.trim() ?? "";
  const started = info.started ?? info.created;
  const elapsed = (info.finished ?? now) - started;

  return (
    <Card className={cn("flex flex-col gap-3 p-4", active && "bg-main-soft", failed && "bg-danger-soft")}>
      <div className="flex items-center gap-2.5">
        <span
          className={cn(
            "grid size-7 flex-none place-items-center rounded-base border-2 border-ink [&_svg]:size-4",
            STATUS_COLOR[info.status],
          )}
        >
          {STATUS_ICON[info.status]}
        </span>
        <div className="flex min-w-0 flex-col leading-tight">
          <strong className="truncate font-black">{info.title}</strong>
          <span className="text-xs text-muted">
            {STATUS_TEXT[info.status]}
            {info.started ? ` · ${formatElapsed(elapsed)}` : ""}
          </span>
        </div>
        <span className="flex-1" />
        {active ? (
          <Button size="sm" onClick={() => setConfirming(true)}>
            取消
          </Button>
        ) : null}
      </div>
      {info.status === "queued" ? (
        <p className="text-muted">任务一个接一个地运行，前面还有 {info.ahead} 个任务。</p>
      ) : null}
      {info.status === "running" ? (
        <div className="flex flex-col gap-1.5">
          {stage ? (
            <div className="text-label font-extrabold">
              {stage}
              {progress ? `（${progress[0]}/${progress[1]}）` : ""}
            </div>
          ) : null}
          <Progress
            label={stage || info.title}
            value={progress ? (100 * progress[0]) / Math.max(progress[1], 1) : null}
          />
          {last ? <div className="truncate text-xs text-muted">{last}</div> : null}
        </div>
      ) : null}
      {failed ? (
        <Alert tone="error">
          <span className="whitespace-pre-wrap">{info.error}</span>
        </Alert>
      ) : null}
      {lost ? <p className="text-muted">网页后台重启过，这个任务的记录已经没有了。</p> : null}
      {cancelError ? <p className="text-danger-ink">{cancelError}</p> : null}
      {lines.length ? (
        <Disclosure title={`运行日志（${lines.length} 行）`} size="sm" open={logOpen} onOpenChange={setLogOpen}>
          <pre
            ref={logRef}
            className="max-h-86 overflow-y-auto rounded-base border-2 border-ink bg-ink p-2.5 text-xs text-terminal"
            onScroll={(e) => {
              const el = e.currentTarget;
              stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
            }}
          >
            {lines.join("\n")}
          </pre>
        </Disclosure>
      ) : null}
      {confirming ? (
        <Dialog
          title="取消任务"
          onClose={() => setConfirming(false)}
          actions={
            <>
              <Button onClick={() => setConfirming(false)}>继续运行</Button>
              <Button variant="primary" onClick={cancel}>
                确定取消
              </Button>
            </>
          }
        >
          <p>确定取消「{info.title}」吗？已经生成的图片会保留。</p>
        </Dialog>
      ) : null}
    </Card>
  );
};
