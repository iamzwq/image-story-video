import { AudioLines, FileUp, Save, Sparkles, Zap } from "lucide-react";
import React, { useRef, useState } from "react";
import type { EpisodeSummary, Ready, StoryboardOptions } from "./api";
import { errorText, formatElapsed, request, speechSeconds } from "./api";
import {
  Alert,
  Button,
  buttonClass,
  Card,
  CardTitle,
  Checkbox,
  Disclosure,
  Field,
  Hint,
  Input,
  Page,
  PageHeader,
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const created = useRef(false);
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

  const seconds = speechSeconds(text);
  const llmMissing = ready !== null && !ready.llm;
  const imageMissing = ready !== null && !ready.image;

  return (
    <Page>
      <PageHeader
        title="新建视频"
        subtitle="粘贴口播文案，AI 会把它分成一个个画面、配音、出图，最后导出带字幕的视频。"
      />
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(320px,1fr)]">
        <Card className="flex flex-col gap-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="标题" hint="显示在视频顶部和封面上">
              <Input value={title} maxLength={60} placeholder="例如：负荆请罪" onChange={(e) => setTitle(e.target.value)} />
            </Field>
            <Field label="副标题（可不填）" hint="开场时显示在标题下面">
              <Input value={subtitle} maxLength={60} onChange={(e) => setSubtitle(e.target.value)} />
            </Field>
          </div>
          <Field
            label="文案"
            hint={
              text.trim()
                ? `${text.length} 字，配音大约 ${formatElapsed(seconds)}`
                : "纯文字或 Markdown 都可以，格式符号、网址、Emoji 不会读出来"
            }
          >
            <Textarea
              className="min-h-86 text-reading"
              value={text}
              rows={18}
              placeholder={"战国时期，赵国有两位名臣……\n\n## 第一章：完璧归赵\n（用 ## 小标题或「第一章：……」分章节，会显示章节卡）"}
              onChange={(e) => setText(e.target.value)}
            />
          </Field>
          <div>
            <label className={buttonClass()}>
              <FileUp />
              从文件导入（.md / .txt）
              <input
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
            </label>
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

        <Card className="flex flex-col gap-4">
          <CardTitle className="mb-0"><AudioLines />配音和画面</CardTitle>
          <StoryboardOptionsForm value={options} onChange={setOptions} compact />
          <div className="h-0.5 bg-ink" />
          <div className="flex flex-col gap-2.5">
            <Button variant="primary" block disabled={busy || llmMissing} onClick={() => create("storyboard")}>
              {busy ? <Spinner /> : <Sparkles />}
              保存并让 AI 写分镜
            </Button>
            <Hint>推荐：写好分镜后先看一遍画面描述、试画几张图，满意了再全部生成。写分镜通常 1–3 分钟。</Hint>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <Button className="flex-1" disabled={busy || llmMissing || imageMissing} onClick={() => create("make")}>
                <Zap />
                一键生成视频
              </Button>
              <CostLimit value={maxCost} onChange={setMaxCost} label="出图费用上限" />
            </div>
            <Checkbox checked={noRefs} onChange={setNoRefs} disabled={busy}>
              不带参考图：省钱，人物前后一致性差一些
            </Checkbox>
            <Hint>
              不用管中间步骤，从分镜一直做到导出。5 分钟的视频大约要 15–30 分钟，出图约 5–10 元；预计超过上限就不出图，不会花钱。
            </Hint>
            <Button variant="link" className="self-start" disabled={busy} onClick={() => create(null)}>
              <Save />
              只保存文案
            </Button>
          </div>
          {llmMissing || imageMissing ? (
            <Alert tone="warn">
              {llmMissing ? "还没有填写大模型设置，没法写分镜。" : `还不能出图：${ready?.imageError}`}{" "}
              <SettingsLink />
            </Alert>
          ) : null}
          {error ? <Alert tone="error">{error}</Alert> : null}
        </Card>
      </div>
    </Page>
  );
};
