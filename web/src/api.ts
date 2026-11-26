import type { Timeline } from "../../src/types";

export type Motion = "zoomIn" | "zoomOut" | "panLeft" | "panRight" | "panUp" | "panDown";

/** storyboard.json 里的一个分镜（章节卡的 type 是 chapter） */
export type Scene = {
  id: string;
  type?: "chapter";
  kicker?: string;
  title?: string;
  hold?: number;
  visual?: string;
  prompt?: string;
  cast?: string[];
  follow?: string;
  reuse?: string;
  motion?: Motion;
  lines: string[];
};

/** storyboard.json；网页只改认识的字段，其余原样保存 */
export type Storyboard = {
  title?: string;
  subtitle?: string;
  aspect?: string;
  voice?: string;
  rate?: string;
  pronunciation?: Record<string, string>;
  imageStyle?: string;
  cast?: Record<string, string>;
  scenes: Scene[];
  [key: string]: unknown;
};

export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";

export type Job = {
  id: string;
  episode: string;
  kind: string;
  title: string;
  status: JobStatus;
  created: number;
  started: number | null;
  finished: number | null;
  error: string;
  ahead: number;
  lineCount: number;
};

export type JobLog = Job & { lines: string[]; offset: number; truncated: boolean };

export type Stage = "script" | "draft" | "images" | "ready" | "done";

export type OutFile = { name: string; url: string; size: number; mtime: number; stale?: boolean };

export type EpisodeSummary = {
  id: string;
  title: string;
  subtitle: string;
  stage: Stage;
  hasScript: boolean;
  hasStoryboard: boolean;
  storyboardError: string;
  draft: boolean;
  hasStyle: boolean;
  imageCount: { need: number; have: number };
  duration: number | null;
  video: OutFile | null;
  cover: OutFile | null;
  job: Job | null;
};

export type SceneImage = { url: string; prompt: string | null; model: string | null };

export type EpisodeDetail = EpisodeSummary & {
  script: { name: string; text: string } | null;
  storyboard: Storyboard | null;
  sceneImages: Record<string, SceneImage>;
  castImages: Record<string, string>;
  timeline: Timeline | null;
  timelineVersion: string | null;
  durations: Record<string, number>;
};

export type Ready = { llm: boolean; image: string | null; imageError: string; ffmpeg: boolean };

export type EpisodeList = { episodes: EpisodeSummary[]; ready: Ready };

export type SettingValue = { set: boolean; override: boolean; value?: string; hint?: string };

export type ModelInfo = { id: string; price: number | null; refs: number; refPrice: number; refFree: number };

export type Settings = {
  values: Record<string, SettingValue>;
  models: { bailian: ModelInfo[]; ark: ModelInfo[] };
  ready: Ready;
};

export type Estimate = {
  count: number;
  ids: string[];
  sheets: string[];
  refs: number;
  cost: number;
  priceKnown: boolean;
  provider: string;
  refsSupported: boolean;
};

export type StoryboardOptions = { voice: string; rate: string; aspect: string; images: number | null };

export class RequestError extends Error {
  status: number;
  code: string;

  constructor(message: string, status: number, code = "") {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export const request = async <T>(path: string, method = "GET", body?: unknown): Promise<T> => {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      cache: "no-store",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new RequestError("连不上网页后台：请确认运行 npm run web 的终端窗口还开着", 0);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new RequestError(data?.error ?? `请求失败（HTTP ${res.status}）`, res.status, data?.code ?? "");
  }
  return data as T;
};

export const errorText = (err: unknown) => (err instanceof Error ? err.message : String(err));

export const errorCode = (err: unknown) => (err instanceof RequestError ? err.code : "");

export const isActive = (job: Job | null | undefined) => job?.status === "queued" || job?.status === "running";

export const formatDuration = (seconds: number) => {
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

export const formatElapsed = (seconds: number) => {
  const s = Math.max(0, Math.floor(seconds));
  return s < 60 ? `${s} 秒` : `${Math.floor(s / 60)} 分 ${s % 60} 秒`;
};

export const formatSize = (bytes: number) =>
  bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;

export const formatTime = (epochSeconds: number) =>
  new Date(epochSeconds * 1000).toLocaleString("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

/** 中文口播大约每秒 4.5 个字 */
export const speechSeconds = (text: string) => (text.match(/[\p{L}\p{N}]/gu)?.length ?? 0) / 4.5;
