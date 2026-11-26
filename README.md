# 配音驱动的图文口播视频

把一篇口播文案自动做成「配音 + 图片 + 字幕」的竖屏视频（1080×1920）。视频以配音为时间轴：先配音，再按每句话的时长安排字幕和图片。

**流程**：文案 → 分镜 → 配音、字幕、时间线 → 出图 → 导出 MP4 和封面。运行 `npm run web` 打开网页版，在浏览器里点一点就能做完；也可以用命令行一条命令做完或分步做，见「[命令行制作视频](docs/cli.md)」。

**成片示例**：

<table>
  <tr>
    <th>《卖火柴的小女孩》</th>
    <th>《负荆请罪》</th>
    <th>《凌晨三点的来电》</th>
  </tr>
  <tr>
    <td>

https://github.com/user-attachments/assets/e3a967f2-e85a-49ee-ac62-78cd4f97962f

</td>
    <td>

https://github.com/user-attachments/assets/d404283a-81d3-479d-8600-b31caffdb32c

</td>
    <td>

https://github.com/user-attachments/assets/e88e4141-99df-4f2b-9fe0-1773e3ac48c4

</td>
  </tr>
</table>

## 适合做什么视频

画面是 AI 插画（每 5–10 秒一张，镜头缓慢推拉），图里没有文字，一集只有一个配音音色。所以适合闭上眼睛也能听懂的讲解和故事：

- **适合**：历史人文（朝代、制度、人物、典故）、讲故事（神话、成语、民间故事、未解之谜）、概念解读（哲学、心理学、「为什么……」）、诗词与传统文化、读书和思想史、科幻等虚构设定。
- **不太适合**：教程、测评、带货（要看真实画面）；财经数据、讲题（离不开图表和公式）；时事新闻、现代真实人物（容易误导，还涉及肖像权）；地图推演；搞笑段子、多角色对话（靠表演，一集只有一个音色）。

拿不准时问自己：闭上眼睛能听懂吗？每 5–10 秒的内容能想象出一张不带字的画吗？画得不准要紧吗？

画风由大模型按内容推荐；默认的音色和分镜提示词按历史题材调过，做其他题材时见「[常见问题](#常见问题)」。

## 快速开始

### 1. 准备环境

1. 安装 Node.js，装完重新打开 VS Code（或终端）：
   ```powershell
   winget install OpenJS.NodeJS.LTS
   ```
   Mac 上用 `brew install node`。
2. 在项目文件夹里运行 `npm install`。

还要用到 uv 和 FFmpeg，不用先装：运行 `npm run web` 时会检查，没有的话问你要不要帮忙安装（Windows 用 winget，Mac 用 Homebrew），装好就接着启动，不用重开终端。想自己装的话：`winget install astral-sh.uv`、`winget install Gyan.FFmpeg`（Mac 上 `brew install uv ffmpeg`）。

第一次运行会自动下载 Python、配音组件和约 130 MB 的渲染用浏览器，需要联网；不需要独立显卡。

### 2. 启动网页

```powershell
npm run web
```

先检查 uv 和 FFmpeg、构建网页，再启动后台，并自动在浏览器里打开 http://127.0.0.1:3100 。用完关掉这个终端窗口就行。

| 参数 | 作用 | 默认 |
| --- | --- | --- |
| `--port <端口>` | 网页端口，被占用时换一个，如 `npm run web -- --port 3200` | `3100` |
| `--no-open` | 启动后不自动打开浏览器 | 自动打开 |
| `--host <地址>` | 监听地址。改成 `0.0.0.0` 局域网里的电脑也能打开，但网页没有登录，能打开的人都能用你的 API Key 花钱 | `127.0.0.1` |

改网页代码时：先运行 `npm run web`，再另开终端运行 `npm run web:dev`（热更新，接口转发给 3100 端口）。

### 3. 做一个视频

1. **设置**：第一次用先到「设置」填写大模型和生图平台的 API Key（见「[API 配置](#api-配置)」），可以测试大模型连不连得上。内容保存在项目根目录的 `.env`。
2. **新建视频**：粘贴文案或导入 .md / .txt 文件（写法见「[文案怎么写](#文案怎么写)」），选配音音色（可以试听）、语速、画面比例和图片张数。
3. **写分镜**：AI 会纠正读音、推荐画风、设计人物，再把文案分成一个个画面并写好出图提示词，通常 1–3 分钟。写好后逐个画面检查，台词、出图提示词、画风、角色外貌、读音、镜头运动都可以直接改，保存后自动重新配音。
4. **出图**：先试画 4 张看画风和人物，满意再生成全部。出图前显示预计费用，可以设上限；不满意的画面改好提示词后单独重画。
5. **预览、导出**：在网页里直接播放，满意后导出 MP4 和封面（存在 `out/`），点「打开所在文件夹」就能找到成片，也可以在网页上下载。

也可以点「一键生成视频」，从写分镜一直做到导出，中途不用操作。7 分钟左右的视频大约要 15–30 分钟，出图约 5–10 元。

- 写分镜、出图、导出都在后台运行，一次运行一个，其余排队。关掉网页不影响后台任务；关掉运行 `npm run web` 的终端窗口，任务才会停止。
- 网页没有登录，默认只允许本机访问。
- 停顿、背景音乐、复用前面的图片等少数设置网页上还没有入口，要直接改分镜文件，见命令行文档的「[修改视频内容](docs/cli.md#修改视频内容)」。
- 想用命令行做（批量处理、对比生图模型、导出样片等），见「[命令行制作视频](docs/cli.md)」。网页和命令行用的是同一套文件（`texts/`、`public/episodes/`、`out/`），可以混着用。

### 文案怎么写

纯文字或 Markdown 都可以。新建视频时文案保存为 `texts/<集数>.标题——副标题.md`（`——` 前面是标题，后面是副标题，都显示在视频开头）；导入文件时，文件名会自动填成标题和副标题。

- **章节**：`第一章：……` 这样的行和 Markdown 小标题（`## ……`）会变成章节卡并读出来，开头的「一、」「（三）」这类序号只显示不读。单独一行的 `结尾`、`总结` 只显示不读；文案最开头的一级标题（`# ……`）不读。
- **格式符号会自动去掉**：加粗、列表、引用、表格、链接、图片、HTML、Emoji、网址、话题标签等都不会读出来，也不会出现在字幕里。
- **拍摄提示要先删掉**：「（停顿）」「【画面：……】」这类写给自己看的提示会被当成台词读出来。

## API 配置

在网页的「设置」里填写最方便，也可以按 `.env.example` 的说明直接编辑 `.env`，两边是同一个文件。`.env` 只保存在你自己的电脑上，不要发给别人；预览和导出读取的是 `remotion.env`，不会接触密钥。

**大模型**（写分镜用）：任何兼容 OpenAI 协议的服务都可以，`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 都要填，例如 DeepSeek：`LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-flash`。写一集分镜通常只要几分钱。

**出图平台**：只需要填 Key，接口地址（北京地域）和默认模型已内置。两个都配了的话，在「设置」里选中的是默认平台（`.env` 里是 `IMAGE_PROVIDER=bailian` 或 `ark`）；用其他地域时在「接口地址」里改（`.env` 里是 `DASHSCOPE_BASE_URL`、`ARK_BASE_URL`）。

| 平台 | 配置 | 默认模型 |
| --- | --- | --- |
| 阿里云百炼（千问生图、Z-Image） | `DASHSCOPE_API_KEY`，换模型改 `DASHSCOPE_IMAGE_MODEL` | `z-image-turbo` |
| 火山引擎方舟（Seedream，即梦/豆包同款） | `ARK_API_KEY`（要先在控制台开通模型），换模型改 `ARK_IMAGE_MODEL` | `doubao-seedream-5-5-261028` |

**参考价格**（2026 年 11 月官网价，9:16、约 2K；以官网为准，审核没通过或失败的不收费）：

| 模型 | 元/张 | 参考图 | 一集（50 多张，含定妆图和参考图） |
| --- | --- | --- | --- |
| `z-image-turbo` | 0.10（北京地域开通后 90 天内免费 100 张） | 不支持 | 约 5 元 |
| `qwen-image-3.0` | 0.18（免费 10 张） | 每张 0.02 元 | 约 11 元 |
| `qwen-image-3.0-pro` | 0.25（免费 10 张） | 每张 0.02 元 | 约 15 元 |
| `doubao-seedream-5-5` | 0.13 | 每张 0.05 元 | 约 10 元（出图时勾选「不带参考图」约 7 元） |
| `doubao-seedream-5-0-flash-260915` | 0.12 | 不收费 | 约 7 元 |

**怎么选**：看重人物前后一致，选支持参考图的 Seedream 或 qwen-image-3.0；只求便宜，z-image-turbo 也够用。拿不准的话，可以用命令行的 `--compare` 让几个模型各出 4 张对比，见「[命令行制作视频](docs/cli.md#npm-run-images调用-api-出图)」。

## 相关网址

需要先注册并实名认证。价格、免费额度会变动，以官网为准。

| 用途 | 阿里云百炼 | 火山引擎方舟 |
| --- | --- | --- |
| 控制台 | [百炼控制台](https://bailian.console.aliyun.com/) | [方舟控制台](https://console.volcengine.com/ark) |
| 开通模型、创建 API Key | [获取 API Key](https://help.aliyun.com/zh/model-studio/get-api-key) | [开通模型](https://ark.volcengine.com/region:cn-beijing/openManagement)、[API Key](https://ark.volcengine.com/region:cn-beijing/apiKey) |
| 模型价格 | [百炼价格](https://help.aliyun.com/zh/model-studio/model-pricing) | [方舟价格](https://docs.volcengine.com/docs/ark/model-pricing?lang=zh) |
| 提示词指南 | [文生图提示词](https://help.aliyun.com/zh/model-studio/text-to-image-prompt) | [Seedream 提示词](https://ark.volcengine.com/region:cn-beijing/docs/seedream-4-0-5-0-prompt-guide) |
| 免费额度 | [新人免费额度、用完即停](https://help.aliyun.com/zh/model-studio/new-free-quota) | — |

## 项目文件

| 路径 | 说明 |
| --- | --- |
| `texts/<集数>.标题——副标题.md` | 口播文案 |
| `public/episodes/<集数>/storyboard.json` | 分镜，网页上改的内容都保存在这里 |
| `public/episodes/<集数>/images/` | 图片，按分镜编号命名；`cast/` 里是角色定妆图；`_generated.json` 记录每张图是怎么生成的 |
| `public/episodes/<集数>/compare/` | 命令行 `--compare` 的对比图，选定后可以删掉 |
| `public/episodes/<集数>/` 里的其他文件 | 配音、时间线、字幕和 `prompts.md`，都是自动生成的，不要手改 |
| `out/` | 导出的成片和封面 |
| `.env`、`.env.example` | 你的 API Key 和配置模板 |
| `remotion.env` | 预览和导出读取的环境变量文件，保持为空 |
| `scripts/` | `make_video.py` 一键生成，`gen_storyboard.py` 写分镜，`build_episode.py` 配音和时间线，`gen_images.py` 出图，`make_cover.py` 封面 |
| `web/` | 网页版：`launch.mjs` 是 `npm run web` 的入口，检查 uv 和 FFmpeg、构建网页、启动后台；`server.py` 是后台，负责读写设置、排队运行 `scripts/` 里的脚本；`src/` 是网页（React + Tailwind CSS + Base UI，neobrutalism 风格，通用组件在 `src/components/ui/`），预览直接用 `src/` 里的视频模板 |
| `src/` | Remotion 视频模板，封面样式在 `Cover.tsx` |
| `public/fonts/` | 思源黑体、思源宋体（SIL OFL 协议，可免费商用） |
| `docs/cli.md` | 命令行制作视频的教程和命令参考 |

## 常见问题

**一键生成后有几个画面重复？** 那几张图没生成出来（通常是审核没过），暂时用了相邻画面。在「画面」列表上方点「缺图」筛选出来，改好提示词后点画面上的「出图」，再重新导出。

**以前写的分镜，人物前后不一致？** 角色表是新写分镜时才有的。在「更多操作」里点「AI 重写分镜」，再点「全部重画」（分镜编号会重排，会重新收费）。只想换画风的话，点「AI 重新推荐画风」。

**想少出几张图？** 新建视频时「图片张数」选「指定张数」。已有分镜的，在「AI 重写分镜」里指定张数，原来的图片对不上，要重画。

**想做历史以外的题材？** 画风会按内容推荐。默认音色是云希（年轻男声，适合讲故事）；做历史、科普可以换成新闻腔的云扬，情感类可以换成晓晓（新建视频时选，已有分镜在「整体设置」里改）。`scripts/gen_storyboard.py` 开头的 `SYSTEM_PROMPT`、`CAST_PROMPT`、`STYLE_PROMPT` 是按历史题材写的，可以让 AI 助手改成对应题材的要求和例子；想让整个系列固定一种画风，也在 `STYLE_PROMPT` 里写明。

**出图很慢？** 生成一张图通常 10–20 秒，慢多半是慢在下载：百炼返回 PNG（约 3 MB），方舟返回 JPEG（约 0.5 MB）。

**独立显卡能加快吗？** 基本不能：分镜、配音、出图都在云端，只有导出在本机，主要靠 CPU。有 NVIDIA 显卡时，用命令行导出可以开硬件加速，最多快四分之一左右，见「[命令行制作视频](docs/cli.md#常见问题)」。

**想换成付费配音或真人录音？** 要改 `scripts/build_episode.py` 的配音部分；用真人录音的话，字幕时间可以改用 Whisper 识别。

## 注意事项

- 配音用 edge-tts（微软 Edge「大声朗读」的在线服务）：免费、不用密钥，但要联网，文案会发给微软；它不是官方开放接口，以后可能失效。
- 用大模型和生图 API 时，文案和提示词会发给对应平台，并经过内容审核。
- API Key 只能放在 `.env`，不要写进 `remotion.env`：Remotion 默认会把 `.env` 写进预览页面，而预览服务会监听局域网地址。
- 配音会自动统一响度（成片约 -15 LUFS），适合短视频平台。`.npmrc` 使用 npmmirror 国内镜像。
- 发布前自查：朝代服饰、器物有没有穿越，背景音乐有没有授权；图片和配音是 AI 生成的，要按平台要求声明。
- Remotion 对个人和 3 人以内的公司免费，更大的团队需要购买授权，见 [remotion.pro/license](https://www.remotion.pro/license)。
