import { Check, Play, Plus, Settings } from "lucide-react";
import React, { useCallback, useEffect, useState } from "react";
import type { EpisodeList, Ready } from "./api";
import { formatDuration, request } from "./api";
import { Alert, Button, buttonClass, Card, Page, PageHeader } from "./components/ui";
import { EpisodePage } from "./EpisodePage";
import { navigate, useInterval, useRoute } from "./hooks";
import { cn } from "./lib/cn";
import { NewEpisodePage } from "./NewEpisodePage";
import { SettingsPage } from "./SettingsPage";
import { SettingsLink, StageBadge } from "./ui";

const navItem = (active: boolean) =>
  cn(
    "flex items-center gap-2.5 rounded-base border-2 border-ink px-2 py-1.5 font-normal text-ink no-underline transition-[background-color,box-shadow,translate] duration-100",
    active
      ? "bg-main shadow-brutal hover:bg-main"
      : "bg-paper hover:-translate-x-px hover:-translate-y-px hover:bg-main-soft hover:shadow-brutal-sm",
  );

const navId = "min-w-[34px] flex-none rounded-[4px] border-2 border-ink bg-white px-1 text-center font-mono text-[11px] font-bold";

export const App: React.FC = () => {
  const route = useRoute();
  const [list, setList] = useState<EpisodeList | null>(null);
  const [offline, setOffline] = useState(false);

  const refresh = useCallback(() => {
    request<EpisodeList>("/api/episodes")
      .then((data) => {
        setList(data);
        setOffline(false);
      })
      .catch(() => setOffline(true));
  }, []);
  useEffect(refresh, [refresh, route]);
  useInterval(refresh, 4000);

  const ready = list?.ready ?? null;
  const setupMissing = ready !== null && (!ready.llm || !ready.image);

  return (
    <div className="grid min-h-screen md:grid-cols-[248px_minmax(0,1fr)]">
      <aside className="flex flex-col gap-4 border-ink bg-white px-3 py-5 max-md:border-b-2 md:sticky md:top-0 md:h-screen md:border-r-2">
        <a className="flex items-center gap-2.5 px-1.5 text-base font-black text-ink no-underline hover:bg-transparent" href="#/">
          <span className="grid size-8 -rotate-6 place-items-center rounded-base border-2 border-ink bg-ink text-main shadow-brutal-sm">
            <Play className="size-4 fill-current" />
          </span>
          图文口播视频
        </a>
        <Button variant="primary" block onClick={() => navigate("/new")}>
          <Plus strokeWidth={3} />
          新建视频
        </Button>
        <nav className="-mx-1 flex flex-1 flex-col gap-2.5 overflow-y-auto px-1 pt-1 pr-2 pb-2">
          {list?.episodes.length ? (
            <div className="px-2 pb-1 text-xs font-extrabold tracking-wider text-muted">我的视频</div>
          ) : null}
          {list?.episodes.map((ep) => (
            <a key={ep.id} href={`#/ep/${ep.id}`} className={navItem(route.page === "episode" && route.id === ep.id)}>
              <span className={navId}>{ep.id}</span>
              <span className="flex min-w-0 flex-col items-start gap-1">
                <span className="max-w-full truncate font-semibold">{ep.title}</span>
                <StageBadge episode={ep} />
              </span>
            </a>
          ))}
        </nav>
        <div className="border-t-2 border-ink pt-3">
          <a href="#/settings" className={cn(navItem(route.page === "settings"), "group")}>
            <span className="flex w-[34px] flex-none justify-center">
              <span className="grid size-7 place-items-center rounded-base border-2 border-ink bg-white shadow-brutal-sm">
                <Settings
                  className="size-4 transition-transform duration-300 group-hover:rotate-90"
                  strokeWidth={2.5}
                />
              </span>
            </span>
            <span className="font-semibold">设置</span>
            {setupMissing ? (
              <span className="ml-auto size-3 rounded-full border-2 border-ink bg-warn" title="还有设置没填" />
            ) : null}
          </a>
        </div>
      </aside>
      <main className="flex min-w-0 flex-col gap-4 px-4 pt-5 pb-28 md:px-8 md:pt-7">
        {offline ? <Alert tone="error">连不上网页后台：请确认运行 npm run web 的终端窗口还开着。</Alert> : null}
        {ready?.ffmpeg === false ? (
          <Alert tone="error">
            没有找到 FFmpeg，配音、出图和导出都没法运行。在运行 npm run web 的终端里按 Ctrl+C 停止，再重新运行 npm run web，会提示帮你安装。
          </Alert>
        ) : null}
        {route.page === "settings" ? (
          <SettingsPage onSaved={refresh} />
        ) : route.page === "new" ? (
          <NewEpisodePage ready={ready} onCreated={refresh} />
        ) : route.page === "episode" ? (
          <EpisodePage key={route.id} id={route.id} ready={ready} onChanged={refresh} />
        ) : (
          <Home list={list} ready={ready} />
        )}
      </main>
    </div>
  );
};

const STEP_COLORS = ["bg-main", "bg-pink", "bg-info", "bg-ok"];

const Home: React.FC<{ list: EpisodeList | null; ready: Ready | null }> = ({ list, ready }) => {
  const settingsDone = Boolean(ready?.llm && ready.image);
  const steps: { title: string; body: React.ReactNode; done?: boolean }[] = [
    {
      title: "填写设置",
      done: settingsDone,
      body: (
        <>
          大模型负责写分镜，生图平台负责画插画。
          {ready && !settingsDone ? (
            <>
              {" "}
              <SettingsLink />
            </>
          ) : (
            " 已经填好了。"
          )}
        </>
      ),
    },
    { title: "新建视频", body: "粘贴文案，选好配音和画面比例。" },
    { title: "写分镜、出图", body: "AI 把文案分成一个个画面并写好提示词；先试画几张看画风，满意再全部生成。" },
    { title: "预览、导出", body: "在网页里直接预览，满意后导出 MP4 和封面。" },
  ];
  return (
    <Page>
      <PageHeader
        title={
          <>
            把一篇文案做成
            <span className="mx-1 inline-block -rotate-2 rounded-base border-2 border-ink bg-main px-2 shadow-brutal-sm">
              短视频
            </span>
          </>
        }
        subtitle="AI 配音 + AI 插画 + 字幕，自动排好时间线，导出竖屏或横屏 MP4 和封面。"
      />
      <Card>
        <ol className="mb-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {steps.map((s, i) => (
            <li key={s.title} className="flex flex-col gap-1.5 rounded-base border-2 border-ink bg-paper p-3.5">
              <span
                className={cn(
                  "grid size-8 place-items-center rounded-base border-2 border-ink text-sm font-black shadow-brutal-sm",
                  s.done ? "bg-ok" : STEP_COLORS[i],
                )}
              >
                {s.done ? <Check className="size-4" strokeWidth={3.5} /> : i + 1}
              </span>
              <strong className="mt-1 text-[15px] font-black">{s.title}</strong>
              <span className="text-muted">{s.body}</span>
            </li>
          ))}
        </ol>
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary" onClick={() => navigate("/new")}>
            <Plus strokeWidth={3} />
            新建视频
          </Button>
          <a className={buttonClass()} href="#/settings">
            <Settings />
            设置
          </a>
        </div>
      </Card>
      {list?.episodes.length ? (
        <section className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-5">
          {list.episodes.map((ep) => (
            <a
              key={ep.id}
              href={`#/ep/${ep.id}`}
              className="group overflow-hidden rounded-base border-2 border-ink bg-white font-normal text-ink no-underline shadow-brutal transition-[translate,box-shadow] duration-100 hover:translate-x-[2px] hover:translate-y-[2px] hover:bg-white hover:shadow-brutal-sm"
            >
              {ep.cover ? (
                <img
                  src={ep.cover.url}
                  alt=""
                  loading="lazy"
                  className="aspect-9/16 max-h-[260px] w-full border-b-2 border-ink bg-ink object-cover"
                />
              ) : (
                <div className="grid aspect-9/16 max-h-[260px] w-full place-items-center border-b-2 border-ink bg-main font-mono text-4xl font-black">
                  {ep.id}
                </div>
              )}
              <div className="flex flex-col items-start gap-1 px-3 pt-2.5 pb-3">
                <strong className="font-black">{ep.title}</strong>
                <span className="text-xs text-muted">
                  第 {ep.id} 集{ep.duration ? ` · ${formatDuration(ep.duration)}` : ""}
                </span>
                <StageBadge episode={ep} />
              </div>
            </a>
          ))}
        </section>
      ) : null}
    </Page>
  );
};
