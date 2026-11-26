import { Bot, Check, ExternalLink, Images, PlugZap, Save, Undo2, WandSparkles, X } from "lucide-react";
import React, { useEffect, useState } from "react";
import type { ModelInfo, Settings } from "./api";
import { errorText, request } from "./api";
import {
  Alert,
  Badge,
  Button,
  buttonClass,
  Card,
  CardTitle,
  Disclosure,
  Field,
  Input,
  Page,
  PageHeader,
  Radio,
  RadioGroup,
  Select,
  Spinner,
} from "./components/ui";
import { PROVIDERS } from "./constants";
import { useLeaveGuard } from "./hooks";
import { cn } from "./lib/cn";

const PLAIN_KEYS = [
  "LLM_BASE_URL",
  "LLM_MODEL",
  "IMAGE_PROVIDER",
  "DASHSCOPE_IMAGE_MODEL",
  "DASHSCOPE_BASE_URL",
  "ARK_IMAGE_MODEL",
  "ARK_BASE_URL",
];
const SECRET_KEYS = ["LLM_API_KEY", "DASHSCOPE_API_KEY", "ARK_API_KEY"];
const URL_FOR_KEY: Record<string, string> = {
  LLM_API_KEY: "LLM_BASE_URL",
  DASHSCOPE_API_KEY: "DASHSCOPE_BASE_URL",
  ARK_API_KEY: "ARK_BASE_URL",
};

const trimSlash = (url: string) => url.trim().replace(/\/+$/, "");

type Form = Record<string, string>;
type ProviderKey = keyof typeof PROVIDERS;

const describeModel = (m: ModelInfo) =>
  [
    m.price !== null ? `约 ${m.price.toFixed(2)} 元/张` : "单价未知",
    m.refs
      ? `支持参考图，人物前后更一致${m.refPrice ? `（每张参考图另收 ${m.refPrice} 元）` : ""}`
      : "不支持参考图，人物前后一致性差一些",
  ].join(" · ");

export const SettingsPage: React.FC<{ onSaved: () => void }> = ({ onSaved }) => {
  const [data, setData] = useState<Settings | null>(null);
  const [form, setForm] = useState<Form>({});
  const [cleared, setCleared] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [test, setTest] = useState<{ running: boolean; ok?: boolean; text?: string }>({ running: false });

  const apply = (s: Settings) => {
    setData(s);
    setForm(
      Object.fromEntries([
        ...PLAIN_KEYS.map((k) => [k, s.values[k]?.value ?? ""]),
        ...SECRET_KEYS.map((k) => [k, ""]),
      ]),
    );
    setCleared({});
  };

  useEffect(() => {
    request<Settings>("/api/settings")
      .then(apply)
      .catch((e) => setStatus({ tone: "error", text: errorText(e) }));
  }, []);

  const dirty =
    data !== null &&
    (PLAIN_KEYS.some((k) => (form[k] ?? "") !== (data.values[k]?.value ?? "")) ||
      SECRET_KEYS.some((k) => form[k] || cleared[k]));
  useLeaveGuard(dirty);

  if (!data) {
    return <Page>{status ? <Alert tone="error">{status.text}</Alert> : <p className="text-muted">加载中…</p>}</Page>;
  }

  const set = (key: string, value: string) => {
    setForm((f) => ({ ...f, [key]: value }));
    setStatus(null);
  };

  const save = async () => {
    const values: Form = {};
    for (const k of PLAIN_KEYS) {
      values[k] = form[k] ?? "";
    }
    for (const k of SECRET_KEYS) {
      if (form[k]) {
        values[k] = form[k];
      } else if (cleared[k]) {
        values[k] = "";
      }
    }
    setSaving(true);
    try {
      apply(await request<Settings>("/api/settings", "PUT", { values }));
      setStatus({ tone: "ok", text: "已保存到项目根目录的 .env" });
      onSaved();
    } catch (e) {
      setStatus({ tone: "error", text: errorText(e) });
    } finally {
      setSaving(false);
    }
  };

  const testLlm = async () => {
    setTest({ running: true });
    try {
      const r = await request<{ ok: boolean; reply?: string; seconds?: number; error?: string }>(
        "/api/settings/test-llm",
        "POST",
        { LLM_BASE_URL: form.LLM_BASE_URL, LLM_API_KEY: form.LLM_API_KEY, LLM_MODEL: form.LLM_MODEL },
      );
      setTest({ running: false, ok: r.ok, text: r.ok ? `连接成功（${r.seconds} 秒），模型回复：${r.reply}` : r.error });
    } catch (e) {
      setTest({ running: false, ok: false, text: errorText(e) });
    }
  };

  const secret = (key: string, placeholder: string) => {
    const info = data.values[key];
    const kept = info?.set && !cleared[key];
    const urlKey = URL_FOR_KEY[key];
    // 换了接口地址时要重新填 Key：后台不会把原来的 Key 发给新地址
    const needNew = kept && !form[key] && trimSlash(form[urlKey] ?? "") !== trimSlash(data.values[urlKey]?.value ?? "");
    return (
      <>
        <div className="flex items-center gap-2">
          <Input
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={form[key] ?? ""}
            placeholder={needNew ? "换了接口地址，请重新填写" : kept ? `已填写（${info.hint}），不修改就留空` : placeholder}
            onChange={(e) => set(key, e.target.value)}
          />
          {kept && !form[key] ? (
            <Button variant="link" onClick={() => setCleared((c) => ({ ...c, [key]: true }))}>
              清除
            </Button>
          ) : null}
          {cleared[key] && !form[key] ? (
            <Button variant="link" onClick={() => setCleared((c) => ({ ...c, [key]: false }))}>
              撤销清除
            </Button>
          ) : null}
        </div>
        {needNew ? <span className="text-xs text-warn-ink">换了接口地址，原来的 Key 不会发给新地址，请重新填写。</span> : null}
      </>
    );
  };

  const override = (key: string) =>
    data.values[key]?.override ? (
      <span className="text-warn-ink">系统环境变量里也设置了 {key}，脚本会优先使用环境变量里的值</span>
    ) : null;

  const providerCard = (key: ProviderKey) => {
    const p = PROVIDERS[key];
    const models = data.models[key];
    const current = form[p.modelVar] || p.defaultModel;
    const info = models.find((m) => m.id === current);
    const custom = !models.some((m) => m.id === form[p.modelVar]) && form[p.modelVar] !== "";
    const isDefault = form.IMAGE_PROVIDER === key;
    return (
      <div
        className={cn(
          "flex flex-col gap-3 rounded-base border-2 border-ink p-4 transition-[background-color,box-shadow]",
          isDefault ? "bg-main-soft shadow-brutal" : "bg-white",
        )}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Radio value={key}>
            <strong className="font-black">{p.label}</strong>
            <span className="text-muted">{p.note}</span>
          </Radio>
          <span className="flex gap-3 text-label">
            {p.links.map((l) => (
              <a key={l.href} href={l.href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5">
                {l.label}
                <ExternalLink className="size-3" strokeWidth={2.5} />
              </a>
            ))}
          </span>
        </div>
        <Field label="API Key" hint={override(p.keyVar)}>
          {secret(p.keyVar, "粘贴 API Key")}
        </Field>
        <Field
          label="模型"
          nativeLabel={false}
          hint={info ? describeModel(info) : "这个模型不在内置价格表里，出图前看不到预计费用"}
        >
          <Select
            value={custom ? "__custom" : current}
            items={[
              ...models.map((m) => ({ value: m.id, label: `${m.id}${m.id === p.defaultModel ? "（默认）" : ""}` })),
              { value: "__custom", label: "其他模型…" },
            ]}
            onChange={(v) => set(p.modelVar, v === "__custom" ? " " : v)}
          />
        </Field>
        {custom ? (
          <Field label="模型名">
            <Input
              value={form[p.modelVar].trim()}
              placeholder="填写平台上的模型名"
              onChange={(e) => set(p.modelVar, e.target.value || " ")}
            />
          </Field>
        ) : null}
        <Disclosure title="接口地址（一般不用改）" size="sm">
          <Field label="接口地址" hint={override(p.urlVar) ?? "默认是北京地域；用其他地域或专属域名时才需要填"}>
            <Input value={form[p.urlVar] ?? ""} placeholder={p.defaultUrl} onChange={(e) => set(p.urlVar, e.target.value)} />
          </Field>
        </Disclosure>
      </div>
    );
  };

  return (
    <Page>
      <PageHeader
        title="设置"
        subtitle="保存在项目根目录的 .env 文件里，只存在你自己的电脑上。不要把 API Key 发给别人。"
      />

      <div className="flex flex-wrap gap-3">
        <Badge tone={data.ready.llm ? "ok" : "warn"} className="px-3 py-1 text-label [&_svg]:size-3.5">
          {data.ready.llm ? <Check strokeWidth={3} /> : <X strokeWidth={3} />}
          {data.ready.llm ? "大模型已填写" : "大模型还没填写，没法写分镜"}
        </Badge>
        <Badge tone={data.ready.image ? "ok" : "warn"} className="px-3 py-1 text-label [&_svg]:size-3.5">
          {data.ready.image ? <Check strokeWidth={3} /> : <X strokeWidth={3} />}
          {data.ready.image ? `出图用 ${data.ready.image}` : data.ready.imageError}
        </Badge>
      </div>

      <Card className="flex flex-col gap-4">
        <div>
          <CardTitle><Bot />大模型</CardTitle>
          <p className="text-muted">
            用来写分镜、推荐画风、设计人物、纠正读音，出图被审核拦下时也用它改写提示词。任何兼容 OpenAI 协议的服务都可以，写一集通常只要几分钱。
          </p>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="接口地址" hint={override("LLM_BASE_URL")}>
            <Input
              value={form.LLM_BASE_URL ?? ""}
              placeholder="https://api.deepseek.com"
              onChange={(e) => set("LLM_BASE_URL", e.target.value)}
            />
          </Field>
          <Field label="API Key" hint={override("LLM_API_KEY")}>
            {secret("LLM_API_KEY", "sk-…")}
          </Field>
          <Field label="模型" hint={override("LLM_MODEL")}>
            <Input value={form.LLM_MODEL ?? ""} placeholder="deepseek-flash" onChange={(e) => set("LLM_MODEL", e.target.value)} />
          </Field>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            onClick={() => {
              set("LLM_BASE_URL", "https://api.deepseek.com");
              set("LLM_MODEL", "deepseek-flash");
            }}
          >
            <WandSparkles />
            填入 DeepSeek 的地址和模型
          </Button>
          <a className={buttonClass({ variant: "link" })} href="https://platform.deepseek.com/api_keys" target="_blank" rel="noreferrer">
            创建 DeepSeek API Key
            <ExternalLink />
          </a>
          <span className="flex-1" />
          <Button variant="dark" onClick={testLlm} disabled={test.running}>
            {test.running ? <Spinner /> : <PlugZap />}
            {test.running ? "测试中…" : "测试连接"}
          </Button>
        </div>
        {test.text ? <Alert tone={test.ok ? "ok" : "error"}>{test.text}</Alert> : null}
      </Card>

      <Card className="flex flex-col gap-4">
        <div>
          <CardTitle><Images />生图</CardTitle>
          <p className="text-muted">
            只需要填 API Key，接口地址和默认模型都已内置。两个平台都填了的话，选中的那个是默认平台。看重人物前后一致，选支持参考图的模型；只求便宜，z-image-turbo 也够用。
          </p>
        </div>
        <RadioGroup
          value={form.IMAGE_PROVIDER ?? ""}
          onChange={(v) => set("IMAGE_PROVIDER", v)}
          className="grid items-start gap-5 lg:grid-cols-2"
        >
          {providerCard("ark")}
          {providerCard("bailian")}
        </RadioGroup>
      </Card>

      <div className="sticky bottom-4 z-20 flex flex-wrap items-center gap-3 rounded-base border-2 border-ink bg-white px-5 py-3 shadow-brutal">
        {status ? (
          <span className={cn("font-semibold", status.tone === "ok" ? "text-ok-ink" : "text-danger-ink")}>{status.text}</span>
        ) : dirty ? (
          <span className="font-semibold">有未保存的修改</span>
        ) : null}
        <span className="flex-1" />
        <Button disabled={!dirty || saving} onClick={() => apply(data)}>
          <Undo2 />
          放弃修改
        </Button>
        <Button variant="primary" disabled={!dirty || saving} onClick={save}>
          {saving ? <Spinner /> : <Save />}
          {saving ? "保存中…" : "保存设置"}
        </Button>
      </div>
    </Page>
  );
};
