import type { Motion, Stage, StoryboardOptions } from "./api";
import type { Tone } from "./components/ui";

export const VOICES = [
  { id: "zh-CN-YunyangNeural", name: "云扬", note: "男声，新闻播报，适合历史、科普" },
  { id: "zh-CN-YunxiNeural", name: "云希", note: "男声，年轻有活力，适合讲故事" },
  { id: "zh-CN-YunjianNeural", name: "云健", note: "男声，浑厚有力，适合纪录片" },
  { id: "zh-CN-XiaoxiaoNeural", name: "晓晓", note: "女声，温暖亲切，适合故事、情感" },
  { id: "zh-CN-XiaoyiNeural", name: "晓伊", note: "女声，活泼，适合童话" },
  { id: "zh-CN-YunxiaNeural", name: "云夏", note: "男童声，适合童话" },
];

export const RATES = ["-10%", "-5%", "+0%", "+5%", "+10%", "+15%", "+20%"];

export const rateLabel = (rate: string) =>
  rate === "+0%" ? "正常语速" : rate === "+5%" ? "+5%（默认，稍快）" : rate.startsWith("-") ? `${rate}（慢一点）` : rate;

export const ASPECTS = [
  { id: "9:16", label: "竖屏 9:16", note: "抖音、视频号、小红书" },
  { id: "16:9", label: "横屏 16:9", note: "B 站、西瓜视频" },
  { id: "3:4", label: "竖屏 3:4", note: "" },
  { id: "1:1", label: "方形 1:1", note: "" },
];

export const MOTIONS: { id: Motion; label: string }[] = [
  { id: "zoomIn", label: "推近" },
  { id: "zoomOut", label: "拉远" },
  { id: "panLeft", label: "左移" },
  { id: "panRight", label: "右移" },
  { id: "panUp", label: "上移" },
  { id: "panDown", label: "下移" },
];

export const STAGES: Record<Stage, { label: string; tone: Tone }> = {
  script: { label: "待写分镜", tone: "muted" },
  draft: { label: "分镜草稿", tone: "warn" },
  images: { label: "待出图", tone: "warn" },
  ready: { label: "可导出", tone: "accent" },
  done: { label: "已完成", tone: "ok" },
};

export const DEFAULT_OPTIONS: StoryboardOptions = { voice: "zh-CN-YunyangNeural", rate: "+5%", aspect: "9:16", images: null };

export const PROVIDERS = {
  ark: {
    label: "火山方舟",
    note: "Seedream，即梦、豆包同款模型",
    keyVar: "ARK_API_KEY",
    modelVar: "ARK_IMAGE_MODEL",
    urlVar: "ARK_BASE_URL",
    defaultModel: "doubao-seedream-5-5-261028",
    defaultUrl: "https://ark.cn-beijing.volces.com/api/v3",
    links: [
      { label: "开通模型", href: "https://ark.volcengine.com/region:cn-beijing/openManagement" },
      { label: "创建 API Key", href: "https://ark.volcengine.com/region:cn-beijing/apiKey" },
    ],
  },
  bailian: {
    label: "阿里云百炼",
    note: "千问生图、Z-Image",
    keyVar: "DASHSCOPE_API_KEY",
    modelVar: "DASHSCOPE_IMAGE_MODEL",
    urlVar: "DASHSCOPE_BASE_URL",
    defaultModel: "z-image-turbo",
    defaultUrl: "https://dashscope.aliyuncs.com",
    links: [
      { label: "百炼控制台", href: "https://bailian.console.aliyun.com/" },
      { label: "获取 API Key", href: "https://help.aliyun.com/zh/model-studio/get-api-key" },
    ],
  },
} as const;
