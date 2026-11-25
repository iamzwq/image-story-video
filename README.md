# 配音驱动的图文口播视频

把一篇口播文案自动做成「配音 + 图片 + 字幕」的竖屏视频（1080×1920）。视频以配音为时间轴：先配音，再按每句话的时长安排字幕和图片。

**流程**：文案 .md → 分镜（storyboard）→ 配音、字幕、时间线（voice）→ 出图（images）→ 导出 MP4（render）和封面（cover）。`npm run make` 一条命令全部完成，也可以分步执行。

**成片示例**：

<table>
  <tr>
    <th>《卖火柴的小女孩》</th>
    <th>《负荆请罪》</th>
  </tr>
  <tr>
    <td>

https://github.com/user-attachments/assets/e3a967f2-e85a-49ee-ac62-78cd4f97962f

</td>
    <td>

https://github.com/user-attachments/assets/d404283a-81d3-479d-8600-b31caffdb32c

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

1. 安装 Node.js、uv、FFmpeg，装完重新打开 VS Code（或终端）：
   ```powershell
   winget install OpenJS.NodeJS.LTS
   winget install astral-sh.uv
   winget install Gyan.FFmpeg
   ```
   Mac 上用 `brew install node uv ffmpeg`。
2. 在项目文件夹里运行 `npm install`。
3. 把 `.env.example` 复制为 `.env`，填写大模型和至少一个生图平台的 API Key（见「[API 配置](#api-配置)」）。

第一次运行会自动下载 Python、配音组件和约 130 MB 的渲染用浏览器，需要联网；不需要独立显卡。

### 2. 一键生成

把文案放进项目根目录的 `texts/` 文件夹，文件名以集数编号开头，例如 `texts/002.《负荆请罪》.md`（`——` 前面是标题，后面是副标题，都显示在视频开头）。然后运行：

```powershell
npm run make -- 002
```

大模型写分镜 → 配音 → 出图 → 导出，成片在 `out/002.mp4`，封面在 `out/002-cover.jpg`。7 分钟左右的视频大约要 15–30 分钟，出图约 5–10 元。中途断了重新运行同一条命令即可，做完的部分不会重做、不会重复花钱。

文案可以用纯文字或 Markdown：

- **章节**：`第一章：……` 这样的行和 Markdown 小标题（`## ……`）会变成章节卡并读出来，开头的「一、」「（三）」这类序号只显示不读。单独一行的 `结尾`、`总结` 只显示不读；文案最开头的一级标题（`# ……`）不读。
- **格式符号会自动去掉**：加粗、列表、引用、表格、链接、图片、HTML、Emoji、网址、话题标签等都不会读出来，也不会出现在字幕里。
- **拍摄提示要先删掉**：「（停顿）」「【画面：……】」这类写给自己看的提示会被当成台词读出来。

### 3. 分步制作

| 步骤 | 命令 | 说明 |
| --- | --- | --- |
| 1. 写分镜 | `npm run storyboard -- 002` | 写完自动生成配音、字幕和 `prompts.md` |
| 2. 检查、修改 | 看 `public/episodes/002/prompts.md`；改了 `storyboard.json` 就运行 `npm run voice -- 002` | 见「[修改视频内容](#修改视频内容)」 |
| 3. 出图 | `npm run images -- 002 --pilot` 先试 4 张，满意后 `npm run images -- 002` | 第一次可以加 `--compare` 对比平台或模型 |
| 4. 预览 | `npm run dev` | 浏览器左侧选 `ep002`，按空格播放；`ep002-cover` 是封面 |
| 5. 导出 | `npm run render -- ep002`，封面 `npm run cover -- 002` | 成片在 `out/002.mp4`，封面在 `out/002-cover.jpg` |

- **没配置大模型**：可以让 AI 助手写分镜（001 就是这样写的），或者运行 `npm run voice -- 002` 按配音时长生成草稿，再自己填写 `imageStyle`（画风）和每个分镜的 `visual`、`prompt`。
- **不用生图 API**：把 `prompts.md` 里的提示词复制到[即梦](https://jimeng.jianying.com/)、[豆包](https://www.doubao.com/)等网页工具，出 9:16 竖图，按分镜编号命名（`S01.jpg`……）放进 `public/episodes/002/images/`，再运行 `npm run voice -- 002`。
- 字幕已经烧在画面里；发布平台支持外挂字幕的话，也可以上传 `captions.srt`。

## 命令参考

所有命令在项目文件夹里运行。**传给脚本的参数要写在 `--` 后面**，例如 `npm run images -- 001 --pilot`，否则参数会被 npm 拿走。

### npm run make：一键生成

依次执行：检查工具和 API Key → 写分镜（已有就跳过）→ 配音和时间线 → 给缺图的分镜出图（不询问费用，预计超过上限时在花钱前停止；被审核拦下的让大模型改写提示词重试一次）→ 导出 → 生成封面。仍然缺图的分镜暂时用相邻画面代替，结束时会列出编号。

| 参数 | 作用 | 默认 |
| --- | --- | --- |
| `--provider <平台>` | 生图平台，写法同 images | `.env` 的 `IMAGE_PROVIDER` |
| `--max-cost <元>` | 出图费用上限 | `20` |
| `--output <路径>` | 成片保存位置，封面存在同一个文件夹（`<文件名>-cover.jpg`） | `out/<集数>.mp4` |
| `--workers <数量>` | 出图时同时发出的请求数 | `2` |
| `--no-refs` | 出图不带参考图，同 images | 带参考图 |
| `--script`、`--voice`、`--rate`、`--aspect`、`--images` | 同 storyboard，只在新写分镜时生效 | — |

已经有分镜时 make 直接沿用。分镜如果是草稿（没有提示词）或者没有画风，make 一开始就会停下，并提示怎么补。

### npm run storyboard：用大模型写分镜

| 参数 | 作用 | 默认 |
| --- | --- | --- |
| `--script <路径>` | 手动指定文案 | `texts/` 里以集数编号开头的 .md |
| `--force` | 已有分镜时重写。旧文件备份为 storyboard.bak.json；分镜编号会重排，旧图片可能对不上 | 已有分镜时拒绝覆盖 |
| `--style` | 只按内容重新推荐画风，改 `imageStyle`（旧文件同样备份） | — |
| `--voice <音色>` | 配音音色 | `zh-CN-YunyangNeural` |
| `--rate <语速>` | 如 `+10%`；放慢时写成 `--rate=-10%` | `+5%` |
| `--aspect <比例>` | `9:16`、`16:9`、`1:1`、`3:4` | `9:16` |
| `--images <张数>` | 整集只用这么多张图，每张对应一段较长的台词。开场和每章至少 1 张，7 分钟的视频建议不少于 15 张 | 每 5–10 秒一张 |

大模型依次做这几件事：

1. **纠正读音**：多音字、生僻字和古代人名、地名（如 `"单于": "蝉于"`），以及所有带阿拉伯数字的说法（如 `"公元前221年": "公元前二百二十一年"`、`"3-5年": "三到五年"`），写进 `pronunciation`，只影响配音。脚本会用拼音字典和数字换算核对，对不上的不采用。
2. **推荐画风**：按题材、时代和基调给整集定一个画风，写进 `imageStyle`，末尾自动加上构图要求（上方留给标题、下方留给字幕、不要出现文字）。
3. **定角色表**：列出反复出现的人物并固定外貌，写进 `cast`；不同时代的同一称呼会拆成不同角色（如「东汉少年皇帝」「明熹宗」）。
4. **写分镜**：按连环画的规则写提示词——用角色名指代人物，同一章节沿用地点和光线，景别有变化，不画拼贴分格；用 `cast` 标出画面里的角色，用 `follow` 标出和上一格接起来的画面。

大模型也会出错，写完后看一遍 `prompts.md`、在预览里听一听，不对的地方直接改 storyboard.json。

### npm run voice：配音、字幕、时间线

改完 storyboard.json 或手动放了图片后运行。只合成改过的句子；台词和停顿都没改时直接沿用上次的配音，一秒左右完成。还没有分镜时，按配音时长生成一份草稿（没有提示词和画风）。

| 参数 | 作用 |
| --- | --- |
| `--redraft` | 按文案重新生成草稿，提示词会清空（旧文件备份为 storyboard.bak.json） |
| `--script`、`--voice`、`--rate`、`--aspect`、`--images` | 同 storyboard，只在生成新草稿时生效；已有分镜的音色、语速、比例直接改 storyboard.json |

分镜写好后再改 .md 文案，脚本只提示两边哪里不一致，不会覆盖分镜。

### npm run images：调用 API 出图

| 参数 | 作用 | 默认 |
| --- | --- | --- |
| `--pilot [张数]` | 从整集均匀挑几张试画风 | 只写 `--pilot` 是 4 张 |
| `--only <编号>` | 只画这些分镜，如 `S07,S22`，已有图片也重画 | — |
| `--force` | 已有图片的分镜也重画 | 跳过已有图片 |
| `--provider <平台>` | `bailian`（或 `qwen`、`aliyun`）、`ark`（或 `seedream`、`doubao`） | `.env` 的 `IMAGE_PROVIDER` |
| `--compare [模型]` | 两个平台各出几张，或对比指定模型（如 `--compare z-image-turbo,qwen-image-3.0`）；存到 `compare/` 并生成对比页，不影响正式图片 | 4 张 |
| `--no-refs` | 不带参考图，角色外貌只写进提示词：省掉参考图的费用，人物一致性差一些 | 带参考图 |
| `--auto-fix` | 被内容审核拦下时让大模型改写提示词重试一次，改写后的提示词写回 storyboard.json | — |
| `--max-cost <元>` | 预计费用超过就停止 | 不限 |
| `--dry-run` | 只列出要画的图和完整提示词，不花钱 | — |
| `--yes`、`-y` | 跳过费用确认 | — |
| `--workers <数量>` | 同时发出的请求数，常被限流时改成 1 | `2` |
| `--keep-png` | 保留 PNG 原图 | 转成 JPEG |

出图前会显示张数和预计费用，输入 `y` 才开始。审核没通过或失败的不收费，结束时会列出编号，改好 `prompt` 后用 `--only` 重画。

**人物前后一致**：分镜有角色表时，先给用到的角色各画一张定妆图（`images/cast/角色名.jpg`），之后每个分镜都把出场角色的定妆图、以及 `follow` 指向的上一格画面作为参考图一起传给生图接口。

- 支持参考图的模型：Seedream 4.0 及以上、qwen-image-3.0（每次最多 3 张）、qwen-image-2.x；`z-image-turbo` 不支持。
- 定妆图不满意：删掉 `images/cast/` 里对应的图，或者改 `cast` 里的外貌（改了外貌或画风会自动重画），再用 `--only` 重画用到这个角色的分镜。也可以按角色名放一张自己准备的图，不会被覆盖。
- 想先看人物是否一致，用 `--only` 挑几个同一角色的画面出图（写完分镜时会提示挑哪几个）。

### 其他命令

```powershell
npm run dev                                          # 预览：左侧选集数，按空格播放；改了文件刷新浏览器即可
npm run dev -- --port=3001                           # 默认端口被占用时换一个
npm run render -- ep001                              # 导出到 out/001.mp4
npm run render -- ep001 out/001-v2.mp4               # 指定文件名
npm run render -- ep001 --frames=0-899               # 只导出前 30 秒，快速检查
npm run render -- ep001 --scale=0.5                  # 半分辨率，适合发样片
npm run cover -- 001                                 # 生成封面 out/001-cover.jpg：第一个画面 + 黑底白字标题（样式在 src/Cover.tsx）
npm run cover -- 001 --output out/001-cover.png      # 指定文件名，可以是 .jpg 或 .png
npx remotion still ep001 out/frame.png --frame=60    # 导出第 2 秒的画面
uvx --from edge-tts edge-tts --list-voices | Select-String zh-CN   # 查看中文音色
npm run lint                                         # 改过 src/ 之后检查视频模板代码
```

## 修改视频内容

视频内容都由 `public/episodes/<集数>/storyboard.json` 决定，改完运行 `npm run voice -- <集数>` 生效。不熟悉 JSON 可以让 AI 助手来改；格式写错时，脚本会提示错在第几行。

| 想要 | 改哪里 |
| --- | --- |
| 改台词 | 分镜的 `lines` |
| 纠正读音 | `pronunciation`，如 `"单于": "蝉于"`、`"221年": "二百二十一年"`，字幕仍显示原文 |
| 换音色、语速 | `voice`、`rate`。常用音色：云扬 `zh-CN-YunyangNeural`（新闻腔）、云希 `zh-CN-YunxiNeural`、云健 `zh-CN-YunjianNeural`、晓晓 `zh-CN-XiaoxiaoNeural` |
| 句间停顿 | `pauses`（秒）：`line` 是同一画面的两句之间，`scene` 是换图时 |
| 某张图停太久或太短 | 把 `lines` 拆到新分镜（起个新编号如 `S12b`，配同名图片），或合并到相邻分镜 |
| 重复使用前面的图 | `"reuse": "S07"` |
| 镜头运动 | `motion`：`zoomIn` `zoomOut` `panLeft` `panRight` `panUp` `panDown`，不写就自动轮换 |
| 背景音乐 | 音乐放进该集文件夹，设置 `"bgm": {"file": "bgm.mp3", "volume": 0.08}` |
| 画风 | `imageStyle`，拼在每条提示词末尾。是空的就没法出图：运行 `npm run storyboard -- 002 --style` 让大模型推荐，或者自己写 |
| 不希望出现的东西 | `negativePrompt`，只有千问生图的 3.0、2.0 系列会用；其他模型要写进 `imageStyle` |
| 画面说明、出图提示词 | `visual`、`prompt` |
| 角色长相 | `cast`（角色表），`"角色名": "外貌设定"`，只写各个画面都不变的特征 |
| 画面里有哪些角色 | 分镜的 `cast`，如 `["东汉少年皇帝"]`，名字和角色表一致；`prompt` 里直接写角色名 |
| 和上一个画面接起来 | 分镜的 `follow`，如 `"follow": "S11"`，出图时参考那一格的场景和光线 |
| 章节卡 | 章节分镜（`"type": "chapter"`）：`lines` 改成 `[]` 就只显示不读，停留秒数用 `hold`（默认 1.8）；显示的文字改 `title`、`kicker` |

改了画风、平台后想把图全部重画：`npm run images -- 002 --force`（会重新收费）。

## API 配置

按 `.env.example` 的说明填写 `.env`。`.env` 只保存在你自己的电脑上，不要发给别人；预览和导出读取的是 `remotion.env`，不会接触密钥。

**大模型**（写分镜用）：任何兼容 OpenAI 协议的服务都可以，`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 都要填，例如 DeepSeek：`LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-flash`。写一集分镜通常只要几分钱。

**出图平台**：只需要填 Key，接口地址（北京地域）和默认模型已内置。两个都配了的话，用 `IMAGE_PROVIDER=bailian` 或 `ark` 指定默认平台；用其他地域时在 `.env` 里加 `DASHSCOPE_BASE_URL` 或 `ARK_BASE_URL`。

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
| `doubao-seedream-5-5` | 0.13 | 每张 0.05 元 | 约 10 元（加 `--no-refs` 约 7 元） |
| `doubao-seedream-5-0-flash-260915` | 0.12 | 不收费 | 约 7 元 |

**怎么选**：看重人物前后一致，选支持参考图的 Seedream 或 qwen-image-3.0；只求便宜，z-image-turbo 也够用。拿不准就用 `npm run images -- 002 --compare 模型1,模型2` 各出 4 张对比。

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
| `public/episodes/<集数>/storyboard.json` | 分镜，修改视频内容就改这里 |
| `public/episodes/<集数>/images/` | 图片，按分镜编号命名；`cast/` 里是角色定妆图；`_generated.json` 记录每张图是怎么生成的 |
| `public/episodes/<集数>/compare/` | `--compare` 的对比图，选定后可以删掉 |
| `public/episodes/<集数>/` 里的其他文件 | 配音、时间线、字幕和 `prompts.md`，都是自动生成的，不要手改 |
| `out/` | 导出的成片和封面 |
| `.env`、`.env.example` | 你的 API Key 和配置模板 |
| `remotion.env` | 预览和导出读取的环境变量文件，保持为空 |
| `scripts/` | `make_video.py` 一键生成，`gen_storyboard.py` 写分镜，`build_episode.py` 配音和时间线，`gen_images.py` 出图，`make_cover.py` 封面 |
| `src/` | Remotion 视频模板，封面样式在 `Cover.tsx` |
| `public/fonts/` | 思源黑体、思源宋体（SIL OFL 协议，可免费商用） |

## 常见问题

**一键生成后有几个画面重复？** 那几张图没生成出来（通常是审核没过），暂时用了相邻画面。改好它们的 `prompt` 后运行 `npm run images -- 002 --only 编号`，再运行 `npm run render -- ep002`。

**以前写的分镜，人物前后不一致？** 角色表是新写分镜时才有的。用 `npm run storyboard -- 002 --force` 重写分镜，再用 `npm run images -- 002 --force` 全部重画（分镜编号会重排，会重新收费）。只想换画风的话，用 `--style`。

**想少出几张图？** 新写分镜时加 `--images`，如 `npm run make -- 002 --images 20`。已有分镜的要先运行 `npm run storyboard -- 002 --force --images 20`，原来的图片对不上，要重画。

**想做历史以外的题材？** 画风会按内容推荐。默认音色云扬是新闻腔，讲故事可以换成晓晓或云希（新写分镜时加 `--voice`，已有分镜改 `voice`）。`scripts/gen_storyboard.py` 开头的 `SYSTEM_PROMPT`、`CAST_PROMPT`、`STYLE_PROMPT` 是按历史题材写的，可以让 AI 助手改成对应题材的要求和例子；想让整个系列固定一种画风，也在 `STYLE_PROMPT` 里写明。

**出图很慢？** 生成一张图通常 10–20 秒，慢多半是慢在下载：百炼返回 PNG（约 3 MB），方舟返回 JPEG（约 0.5 MB）。

**独立显卡能加快吗？** 基本不能：分镜、配音、出图都在云端，只有导出在本机，主要靠 CPU。有 NVIDIA 显卡（驱动 525 以上）时，`npm run render -- ep002 --hardware-acceleration=if-possible --video-bitrate=10M` 最多快四分之一左右；没有 NVIDIA 显卡不要加，会导出失败。

**想换成付费配音或真人录音？** 要改 `scripts/build_episode.py` 的配音部分；用真人录音的话，字幕时间可以改用 Whisper 识别。

## 注意事项

- 配音用 edge-tts（微软 Edge「大声朗读」的在线服务）：免费、不用密钥，但要联网，文案会发给微软；它不是官方开放接口，以后可能失效。
- 用大模型和生图 API 时，文案和提示词会发给对应平台，并经过内容审核。
- API Key 只能放在 `.env`，不要写进 `remotion.env`：Remotion 默认会把 `.env` 写进预览页面，而预览服务会监听局域网地址。
- 配音会自动统一响度（成片约 -15 LUFS），适合短视频平台。`.npmrc` 使用 npmmirror 国内镜像。
- 发布前自查：朝代服饰、器物有没有穿越，背景音乐有没有授权；图片和配音是 AI 生成的，要按平台要求声明。
- Remotion 对个人和 3 人以内的公司免费，更大的团队需要购买授权，见 [remotion.pro/license](https://www.remotion.pro/license)。
