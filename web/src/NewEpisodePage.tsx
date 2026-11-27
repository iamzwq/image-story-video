import { AudioLines, Clapperboard, FileText, FileUp, Save, Sparkles, Zap } from "lucide-react";
import React, { useRef, useState } from "react";
import type { EpisodeSummary, Ready, StoryboardOptions } from "./api";
import { errorText, formatElapsed, request, speakableChars, speechSeconds } from "./api";
import {
  Alert,
  Button,
  Card,
  CardTitle,
  Checkbox,
  Disclosure,
  Field,
  Input,
  Page,
  PageHeader,
  Radio,
  RadioGroup,
  Spinner,
  Textarea,
} from "./components/ui";
import { DEFAULT_OPTIONS } from "./constants";
import { navigate, setFlash, useLeaveGuard } from "./hooks";
import { CostLimit, SettingsLink, StoryboardOptionsForm } from "./ui";

export const NewEpisodePage: React.FC<{ ready: Ready | null; onCreated: () => void }> = ({ ready, onCreated }) => {
  const [title, setTitle] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [text, setText] = useState("");
  const [options, setOptions] = useState<StoryboardOptions>(DEFAULT_OPTIONS);
  const [maxCost, setMaxCost] = useState(20);
  const [noRefs, setNoRefs] = useState(false);
  // 推荐先写分镜、看过画面再出图；一键生成适合已经熟悉效果的时候
  const [mode, setMode] = useState<"storyboard" | "make">("storyboard");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const created = useRef(false);
  const fileInput = useRef<HTMLInputElement>(null);
  useLeaveGuard(Boolean(title.trim() || subtitle.trim() || text.trim()), () => created.current);

  const importFile = async (file: File) => {
    setText((await file.text()).replace(/\r\n?/g, "\n"));
    if (!title.trim()) {
      const name = file.name.replace(/\.(md|markdown|txt)$/i, "").replace(/^\d+[.\s_-]*/, "");
      const [t, s] = name.split("——");
      setTitle(t.trim());
      if (s && !subtitle.trim()) {
        setSubtitle(s.trim());
      }
    }
  };

  const create = async (next: "storyboard" | "make" | null) => {
    if (!title.trim() || !text.trim()) {
      setError("标题和文案都要填写");
      return;
    }
    setBusy(true);
    setError("");
    let episode: EpisodeSummary;
    try {
      episode = await request<EpisodeSummary>("/api/episodes", "POST", { title, subtitle, text, options });
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
      return;
    }
    if (next) {
      try {
        const jobOptions = next === "make" ? { ...options, maxCost, noRefs } : { ...options, maxCost };
        await request(`/api/episodes/${episode.id}/jobs`, "POST", { kind: next, options: jobOptions });
      } catch (e) {
        setFlash(`文案已保存，但没能开始${next === "make" ? "一键生成" : "写分镜"}：${errorText(e)}`);
      }
    }
    onCreated();
    created.current = true;
    navigate(`/ep/${episode.id}`);
  };

  const seconds = speechSeconds(text, options.rate);
  const llmMissing = ready !== null && !ready.llm;
  const imageMissing = ready !== null && !ready.image;
  const making = mode === "make";
  const startBlocked = busy || llmMissing || (making && imageMissing);

  return (
    <Page>
      <PageHeader
        title="新建视频"
        subtitle="粘贴口播文案，选好配音和画面比例。AI 负责分镜、配音和出图，最后导出带字幕的 MP4。"
      />
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(340px,1fr)]">
        <Card className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle className="mb-0">
              <FileText />
              文案
            </CardTitle>
            <Button size="sm" onClick={() => fileInput.current?.click()}>
              <FileUp />
              从文件导入
            </Button>
            <input
              ref={fileInput}
              type="file"
              accept=".md,.markdown,.txt,text/plain,text/markdown"
              hidden
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  importFile(file);
                }
                e.target.value = "";
              }}
            />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="标题" hint="显示在视频顶部和封面上">
              <Input value={title} maxLength={60} placeholder="例如：负荆请罪" onChange={(e) => setTitle(e.target.value)} />
            </Field>
            <Field label="副标题（可不填）" hint="开场时显示在标题下面">
              <Input value={subtitle} maxLength={60} onChange={(e) => setSubtitle(e.target.value)} />
            </Field>
          </div>
          <div className="relative">
            {text.trim() ? (
              <span className="absolute top-0 right-0 text-label font-semibold text-muted">
                {speakableChars(text)} 字 · 配音约 {formatElapsed(seconds)}
              </span>
            ) : null}
            <Field label="正文" hint="纯文字或 Markdown 都可以，格式符号、网址、Emoji 不会读出来">
              <Textarea
                className="min-h-86 text-reading"
                value={text}
                rows={16}
                placeholder={"战国时期，赵国有两位名臣……\n\n## 第一章：完璧归赵\n（用 ## 小标题或「第一章：……」分章节，会显示章节卡）"}
                onChange={(e) => setText(e.target.value)}
              />
            </Field>
          </div>
          <Disclosure title="什么样的文案适合？" size="sm">
            <ul className="flex list-disc flex-col gap-1.5 pl-5 text-muted marker:text-ink">
              <li>
                <strong className="text-ink">适合</strong>：历史人文、讲故事、概念解读、诗词与传统文化等闭上眼睛也能听懂的讲解。画面是每
                5–10 秒一张的 AI 插画，图里没有文字，一集只有一个配音音色。
              </li>
              <li>
                <strong className="text-ink">不太适合</strong>
                ：教程、测评、带货（要看真实画面），财经数据（离不开图表），时事新闻和现代真实人物，多角色对话。
              </li>
              <li>
                「（停顿）」「【画面：……】」这类写给自己看的提示要先删掉，否则会被当成台词读出来。文案里的数字和容易读错的字，AI
                写分镜时会自动纠正读音。
              </li>
            </ul>
          </Disclosure>
        </Card>

        <div className="flex flex-col gap-5">
          <Card className="flex flex-col gap-4">
            <CardTitle className="mb-0">
              <AudioLines />
              配音和画面
            </CardTitle>
            <StoryboardOptionsForm value={options} onChange={setOptions} compact />
          </Card>

          <Card className="flex flex-col gap-4">
            <CardTitle className="mb-0">
              <Clapperboard />
              开始制作
            </CardTitle>
            <RadioGroup
              label="制作方式"
              value={mode}
              onChange={(v) => setMode(v as "storyboard" | "make")}
              className="grid gap-2.5"
            >
              <Radio value="storyboard" className={modeTile}>
                <span className="flex flex-col gap-0.5">
                  <strong className="font-black">先写分镜（推荐）</strong>
                  <span className="text-label text-muted">先看画面描述、试画几张，满意再全部出图。约 1–3 分钟。</span>
                </span>
              </Radio>
              <Radio value="make" disabled={imageMissing} className={modeTile}>
                <span className="flex flex-col gap-0.5">
                  <strong className="font-black">一键生成</strong>
                  <span className="text-label text-muted">从分镜一直做到导出。5 分钟的视频约 15–30 分钟、出图 5–10 元。</span>
                </span>
              </Radio>
            </RadioGroup>
            {making ? (
              <div className="flex flex-col gap-3 border-l-4 border-ink pl-3.5">
                <CostLimit
                  value={maxCost}
                  onChange={setMaxCost}
                  label="出图费用上限"
                  note="（预计超过就不出图，不会花钱）"
                />
                <Checkbox checked={noRefs} onChange={setNoRefs} disabled={busy}>
                  不带参考图：省钱，人物前后一致性差一些
                </Checkbox>
              </div>
            ) : null}
            <Button variant="primary" block disabled={startBlocked} onClick={() => create(mode)}>
              {busy ? <Spinner /> : making ? <Zap /> : <Sparkles />}
              {making ? "保存并一键生成" : "保存并写分镜"}
            </Button>
            <Button variant="link" className="self-center" disabled={busy} onClick={() => create(null)}>
              <Save />
              只保存文案，稍后再做
            </Button>
            {llmMissing || imageMissing ? (
              <Alert tone="warn">
                {llmMissing ? "还没有填写大模型设置，没法写分镜。" : `还不能出图，所以一键生成用不了：${ready?.imageError}`}{" "}
                <SettingsLink />
              </Alert>
            ) : null}
            {error ? <Alert tone="error">{error}</Alert> : null}
          </Card>
        </div>
      </div>
    </Page>
  );
};

// 制作方式的选项卡片：选中的那张填浅主色、带投影
const modeTile =
  "items-start gap-3 rounded-base border-2 border-ink bg-white p-3 transition-[background-color,box-shadow] duration-100 motion-reduce:transition-none " +
  "hover:bg-main-soft has-data-checked:bg-main-soft has-data-checked:shadow-brutal-sm has-data-disabled:opacity-55 has-data-disabled:hover:bg-white [&>button]:mt-0.5";
