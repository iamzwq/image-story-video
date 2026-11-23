# 配音驱动的图文口播视频

把一篇口播文案自动做成「配音 + 图片 + 字幕」的竖屏视频（1080×1920）。视频以配音为时间轴：先配音，再按每句话的时长安排字幕和图片。

**流程**：文案 .md → 分镜（storyboard）→ 配音、字幕、时间线（voice）→ 出图（images）→ 导出 MP4（render）。`npm run make` 一条命令就能全部完成，也可以分步执行。

## 适合做什么视频

这种视频靠配音讲内容，画面只起烘托作用，所以适合闭上眼睛也能听懂的讲解和故事，不适合必须看清真实画面的内容。具体来说：

- 画面是 AI 插画，每 5–10 秒换一张，镜头缓慢推拉或平移，没有真实的视频素材。
- 图片里不能有文字，放不了图表、数据、带标注的地图和公式。字幕、标题和章节卡是视频程序另外叠加的。
- 一集只用一个配音音色，语气平稳，适合讲述，不擅长表演。
- 便宜、出片快，适合做成系列。

| 适合 | 例子 | 原因 |
| --- | --- | --- |
| 历史、人文科普 | 朝代兴衰、制度演变、历史人物、典故 | 本来就没有真实影像，AI 插画正好能还原场景。默认的画风和分镜提示词就是按这类题材设计的 |
| 讲故事 | 神话传说、民间故事、成语典故、山海经、未解之谜、睡前故事 | 每段话都有现成的画面，最容易出图 |
| 概念解读 | 哲学、心理学、经济学常识，「为什么……」这类问题 | 听就能懂；写分镜时会把抽象概念转成具体的场景或象征物 |
| 诗词、传统文化 | 诗词赏析、二十四节气、节日民俗 | 意境图是 AI 插画的强项，默认的中国风画风可以直接用 |
| 读书、思想史 | 名著导读、思想家的生平和观点 | 内容靠讲，画面烘托氛围就够了。以自己的解读为主，不要大段朗读原文 |
| 虚构设定 | 科幻世界观、「如果……会怎样」 | 现实中拍不到，只能靠画 |

| 不太适合 | 原因 |
| --- | --- |
| 教程、做菜、开箱测评、带货 | 观众要看真实的操作和产品 |
| 财经数据、股票、数理化讲题 | 离不开图表、数字和公式 |
| 时事新闻、现代真实人物 | AI 会凭空画出现场和长相，容易误导人，还涉及肖像权 |
| 战争推演、地缘政治 | 需要准确的地图和标注 |
| 搞笑段子、情景剧、多角色对话 | 靠表演和节奏，AI 配音没有喜剧感，而且一集只能用一个音色 |
| 个人 IP、情感陪伴 | 观众的信任来自真人出镜或真人的声音 |

拿不准一篇文案合不合适，可以问自己三个问题：

1. **闭上眼睛听，能完全听懂吗？** 信息只能放在配音里。
2. **每 5–10 秒的内容，能想象出一张不带字的画吗？** 想不出来的话，画面会变成一堆「一个人在沉思」。
3. **画得不准要紧吗？** 只是示意、营造氛围就没问题；画面要当证据（真实的人、产品、数据）就不行。

默认的画风、音色和分镜提示词是按历史题材调的，做其他题材时怎么改，见「[常见问题](#常见问题)」。

## 快速开始

### 1. 准备环境（每台电脑只做一次）

1. 安装 Node.js、uv、FFmpeg 三个工具，装完重新打开 VS Code（或终端）：
   ```powershell
   winget install OpenJS.NodeJS.LTS
   winget install astral-sh.uv
   winget install Gyan.FFmpeg
   ```
   Mac 上用 `brew install node uv ffmpeg`。
2. 在项目文件夹里安装依赖：
   ```powershell
   npm install
   ```
3. 把 `.env.example` 复制一份，改名为 `.env`，填写大模型和至少一个生图平台的 API Key（见「[API 配置](#api-配置)」）。

第一次运行时会自动下载 Python、配音组件和一个约 130 MB 的渲染用浏览器，所以需要联网。不需要独立显卡。

### 2. 一键生成

把文案放在项目根目录，文件名以集数编号开头，例如 `002.皇帝的权力从哪里来——从秦朝说起.md`。`——` 前面是标题，后面是副标题，都会显示在视频开头。

文案可以是纯文字，也可以直接用 Markdown 写：

- **章节**：像 `第一阶段：……`、`第三章：……` 这样的行，以及 Markdown 小标题（`## ……`、`### **一、……**`），会变成章节卡，同时读出来，章节卡一直显示到读完。小标题开头的「一、」「（三）」「4.」这类序号只显示在章节卡上，不读。单独一行的 `结尾`、`总结` 只显示章节卡，不读。文案最开头的一级标题（`# ……`）当作整篇标题，不读（视频标题取自文件名）。
- **格式符号会自动去掉**：加粗、斜体、删除线、高亮、列表、引用、表格、分隔线、代码块、链接（只留文字）、图片、HTML 标签和注释、Emoji、网址、整行的话题标签（`#历史 #皇帝`）都不会读出来，也不会出现在字幕里。只有标点、没有文字的行（如 `……`）会跳过。
- **拍摄提示要先删掉**：像「（停顿）」「【画面：皇宫大殿】」这类写给自己看的提示，会被当成台词读出来。

然后运行：

```powershell
npm run make -- 002
```

接下来全部自动完成：大模型写分镜 → 配音 → 出图 → 导出，成片保存在 `out/002.mp4`。一集 7 分钟左右的视频，大约需要 15–30 分钟（主要花在出图和导出上），出图费用约 5–10 元。

- 中途断了（断网、关机），重新运行同一条命令即可。已经写好的分镜、合成好的配音、生成好的图片都会保留，不会重复花钱。
- 预计出图费用超过 20 元时，会在花钱之前停下（用 `--max-cost` 调整上限）。
- 某张图被平台的内容审核拦下时，会让大模型改写提示词后重试；还是不行，就暂时用相邻的画面代替，运行结束时会列出这些分镜。

001 的分镜已经写好，配好生图平台的 Key 后运行 `npm run make -- 001`，就会直接出图并导出。

### 3. 分步制作（想逐步检查、修改时）

| 步骤 | 命令 | 说明 |
| --- | --- | --- |
| 1. 写分镜 | `npm run storyboard -- 002` | 大模型写分镜，写完自动生成配音、字幕和 `prompts.md` |
| 2. 检查、修改 | 打开 `public/episodes/002/prompts.md` 看一遍；改了 `storyboard.json` 就运行 `npm run voice -- 002` | 见「[修改视频内容](#修改视频内容)」 |
| 3. 出图 | `npm run images -- 002 --pilot` 先试 4 张，满意后运行 `npm run images -- 002` | 第一次用可以先加 `--compare` 对比不同平台或模型 |
| 4. 预览 | `npm run dev` | 在浏览器左侧选 `ep002` 播放，还没有图的分镜显示占位图 |
| 5. 导出 | `npm run render -- ep002` | 成片在 `out/002.mp4` |

- **没配置大模型**：可以在对话里让 AI 助手写分镜（001 就是这样写的）；也可以运行 `npm run voice -- 002` 按配音时长生成草稿，再自己给每个分镜填写 `visual`（画面描述）和 `prompt`（出图提示词）。
- **不用生图 API**：把 prompts.md 里的提示词复制到即梦、豆包、万相等网页工具，出 9:16 竖图，按分镜编号命名（`S01.jpg`、`S02.png`……）放进 `public/episodes/002/images/`，再运行 `npm run voice -- 002`。比例不对或分辨率太低的图，脚本会提示。
- 字幕已经烧在画面里。如果发布平台支持外挂字幕，也可以上传 `public/episodes/002/captions.srt`。

## 命令参考

所有命令都在项目文件夹里运行。**传给脚本的参数要写在 `--` 后面**，例如 `npm run images -- 001 --pilot`。漏掉 `--` 的话，参数会被 npm 自己拿走，脚本收不到。

### 各命令的分工

| 命令 | 什么时候用 | 做什么 | 用到的 AI | 费用 |
| --- | --- | --- | --- | --- |
| `npm run make -- 002` | 想一步到位 | 依次执行下面的 storyboard、voice、images、render，已完成的步骤自动跳过 | 同下面各步 | 一集约 5–10 元，主要是出图 |
| `npm run storyboard -- 002` | 每集开头用一次 | 大模型读文案、写分镜（哪几句合成一个画面、画面描述、出图提示词），并标出容易读错的词，写完自动执行一次 voice | **大模型**（`.env` 里的 `LLM_*`） | 一集几分钱 |
| `npm run voice -- 002` | 改完 storyboard.json 或手动放了图片之后 | 重新生成配音（只合成改过的句子）、字幕、时间线和 prompts.md；还没有分镜时，先按时长生成草稿 | 配音用微软的语音合成模型（由 edge-tts 调用，不是大模型，不用配置）；字幕和时间线由脚本计算 | 免费 |
| `npm run images -- 002` | 分镜写好之后 | 调用生图 API 出图，出完自动执行一次 voice | 生图模型（不是大模型，需要 `DASHSCOPE_API_KEY` 或 `ARK_API_KEY`）；加 `--auto-fix` 时，被审核拦下的提示词交给大模型改写 | 按张收费，默认模型约 0.1 元/张；用方舟 Agent Plan 套餐时扣套餐额度 |
| `npm run dev` | 任何时候 | 打开预览 | 不用 | 免费 |
| `npm run render -- ep002` | 最后 | 导出 MP4 | 不用 | 免费 |

只有两处用到大模型：写分镜，以及出图被审核拦下时改写提示词。没有配置大模型时，分镜可以让 AI 助手写或自己写（见「[分步制作](#3-分步制作想逐步检查修改时)」），其他步骤照常。

storyboard 不是用来代替 voice 的：storyboard 负责「从文案写出分镜」，每集通常只用一次；之后改了 storyboard.json（台词、读音、音色、停顿、提示词等），或者手动放了新图片，都要运行 voice 让改动生效。用 images 出图后会自动执行 voice，不用再手动运行。

### npm run make：一键生成

```
npm run make -- <集数> [参数]
```

依次执行：

1. 检查工具、依赖和 API Key 是否齐全，不齐就直接停下，避免做到一半才失败。
2. 没有 `storyboard.json` 时用大模型写分镜，并标出容易读错的词；已经有了就跳过。
3. 生成配音、字幕和时间线。
4. 只为还没有图片的分镜出图，中途不询问费用（预计超过上限时直接停止）；被审核拦下的会让大模型改写提示词重试一次。
5. 仍然缺图的分镜暂时用相邻画面代替，然后导出 MP4。

| 参数 | 作用 | 默认 |
| --- | --- | --- |
| `<集数>` | 必填 | — |
| `--script <路径>` | 手动指定文案文件 | 自动查找 |
| `--provider <平台>` | 生图平台，写法同 images | `.env` 里的 `IMAGE_PROVIDER`；只配置了一个平台时就用它 |
| `--max-cost <元>` | 出图费用上限，预计超过时在花钱之前停止 | `20` |
| `--output <路径>` | 成片保存位置 | `out/<集数>.mp4` |
| `--workers <数量>` | 出图时同时发出的请求数 | `2` |
| `--voice`、`--rate`、`--aspect` | 新写分镜时使用的音色、语速、画面比例，已有分镜时不生效 | 同 storyboard |

```powershell
npm run make -- 002                           # 最常用的写法
npm run make -- 002 --provider ark            # 用火山方舟出图
npm run make -- 002 --max-cost 30             # 费用上限调到 30 元
npm run make -- 002 --output D:\成片\002.mp4   # 成片保存到别的地方
npm run make -- 001                           # 001 已有分镜，只出图和导出
```

已经有分镜时，make 直接沿用，不会重写。如果这份分镜是 `npm run voice` 生成的草稿（没有提示词），make 会停下来提示：可以运行 `npm run storyboard -- 002 --force` 让大模型重写，或者先补上提示词。

### npm run storyboard：用大模型写分镜

```
npm run storyboard -- <集数> [参数]
```

| 参数 | 作用 | 默认 |
| --- | --- | --- |
| `<集数>` | 必填，脚本会在项目根目录找以它开头的 .md 文案 | — |
| `--script <路径>` | 手动指定文案文件 | 自动查找 |
| `--force` | 已经有 storyboard.json 时重新生成。旧文件备份为 storyboard.bak.json；分镜编号会重新排列，已有的图片可能对不上 | 已有分镜时拒绝覆盖 |
| `--voice <音色>` | 配音音色，写进新分镜 | `zh-CN-YunyangNeural` |
| `--rate <语速>` | 语速，如 `+10%`；放慢时带等号写成 `--rate=-10%` | `+5%` |
| `--aspect <比例>` | 画面比例：`9:16`、`16:9`、`1:1`、`3:4` | `9:16` |

```powershell
npm run storyboard -- 002                              # 最常用的写法
npm run storyboard -- 002 --voice zh-CN-YunxiNeural    # 换成云希的声音
npm run storyboard -- 002 --rate=-10%                  # 语速放慢一些
npm run storyboard -- 002 --aspect 16:9                # 做横屏视频
npm run storyboard -- 002 --script D:\文案\皇帝.md      # 文案不在项目根目录
npm run storyboard -- 002 --force                      # 文案改了，让大模型重写分镜
```

写分镜之前，大模型会先找出配音容易读错的词（读音特殊的多音字、生僻字，以及古代人名、地名、官职等），用同音字写进 `pronunciation`，例如 `"单于": "蝉于"`。替换只影响配音，字幕仍显示原文。脚本会用拼音字典检查：大模型标的拼音不是这几个字的读音之一，或者同音字的读音（包括声调）和拼音对不上，都不会采用，最后列出来供参考。大模型也可能判断错，写完后请在预览里听一下这些词：读得不对就修改或删掉，再运行 `npm run voice -- 002`。这一步只在写分镜时做，已经有分镜的集数要纠正读音，还是在 `pronunciation` 里自己写。

### npm run voice：配音、字幕、时间线

```
npm run voice -- <集数> [参数]
```

| 参数 | 作用 | 默认 |
| --- | --- | --- |
| `<集数>` | 必填 | — |
| `--script <路径>` | 手动指定文案文件 | 自动查找 |
| `--redraft` | 按文案重新生成一份按时长分组的草稿，提示词会清空。旧文件备份为 storyboard.bak.json；分镜编号会重新排列 | 不覆盖 |
| `--voice`、`--rate`、`--aspect` | 同 storyboard，只在生成新草稿时生效。分镜已经存在时，请直接改 storyboard.json 里的 `voice`、`rate`、`aspect` | 同上 |

```powershell
npm run voice -- 001             # 改完 storyboard.json 后刷新，配音有缓存，通常几秒完成
npm run voice -- 002             # 002 还没有分镜时，按时长生成草稿（没有提示词）
npm run voice -- 002 --redraft   # 文案大改后，丢掉旧分镜重新起草
```

分镜写好以后再改 .md 文案，脚本不会覆盖分镜，只会提示两边哪里不一致。可以直接在 storyboard.json 里改对应的台词，也可以用 `--redraft` 或 `npm run storyboard -- 002 --force` 重新生成。

### npm run images：调用 API 出图

```
npm run images -- <集数> [参数]
```

| 参数 | 作用 | 默认 |
| --- | --- | --- |
| `<集数>` | 必填 | — |
| `--pilot [张数]` | 试画风：从整集里均匀挑几个分镜出图 | 不加就出全部缺图；只写 `--pilot` 是 4 张 |
| `--only <编号>` | 只生成这些分镜，逗号分隔，如 `S07,S22`。已有图片也会重画 | — |
| `--force` | 已有图片的分镜也重新生成 | 跳过已有图片 |
| `--provider <平台>` | `bailian`（也可以写 `qwen`、`aliyun`）或 `ark`（也可以写 `seedream`、`doubao`、`jimeng`） | `.env` 里的 `IMAGE_PROVIDER`；只配置了一个平台时就用它 |
| `--compare [模型]` | 不写模型名时，两个平台各出一组图；写模型名（逗号分隔）时，对比这些模型，如 `--compare z-image-turbo,qwen-image-3.0`。图片存到 `compare/` 文件夹并生成对比页，不影响正式图片。重新运行会跳过已经出好的图（加 `--force` 重画） | 只出 4 张 |
| `--auto-fix` | 被内容审核拦下时，让大模型改写提示词后重试一次；成功后新提示词写回 storyboard.json | 不改写 |
| `--max-cost <元>` | 预计费用超过这个数就直接停止 | 不限 |
| `--dry-run` | 只列出要生成哪些图和完整的提示词，不调用接口、不花钱 | — |
| `--yes` 或 `-y` | 跳过费用确认 | 每次都要确认 |
| `--workers <数量>` | 同时发出的请求数，经常被限流时改成 1 | `2` |
| `--keep-png` | 保留平台返回的 PNG 原图 | 转成 JPEG，体积小很多 |

```powershell
npm run images -- 001 --dry-run                   # 先看看要出哪些图、提示词对不对
npm run images -- 001 --compare                   # 第一次用：两家各出 4 张，打开 compare\index.html 对比
npm run images -- 001 --compare z-image-turbo,qwen-image-3.0,qwen-image-3.0-pro   # 对比同一平台的三个模型
npm run images -- 001 --pilot                     # 用默认平台试 4 张
npm run images -- 001 --pilot 6 --provider ark    # 用火山方舟试 6 张
npm run images -- 001                             # 出完所有还没有图的分镜，已有的跳过
npm run images -- 001 --only S07,S22              # 改完这两个分镜的 prompt 后重画
npm run images -- 001 --only S07 --auto-fix       # 被审核拦下的分镜，让大模型改写后重画
npm run images -- 001 --force --provider bailian  # 换平台后全部重画
```

出图前会显示张数和预计费用，输入 `y` 才开始。被内容审核拦下或生成失败的分镜不收费，会单独列出来：改一下它的 `prompt` 再用 `--only` 重画，或者加 `--auto-fix` 让大模型改写。图片生成后，下载中途断开会自动从断点续传，不会重新生成、重复收费。每张图用的平台、模型和提示词记录在 `images/_generated.json`。

### npm run dev：预览

```powershell
npm run dev                  # 打开 Remotion Studio，左侧选 ep001，按空格播放
npm run dev -- --port=3001   # 默认端口被占用时换一个
```

预览开着的时候可以继续运行 voice、images，刷新浏览器就能看到变化。在终端里按 `Ctrl+C` 关闭预览。

### npm run render：导出视频

```powershell
npm run render -- ep001                             # 导出到 out/001.mp4
npm run render -- ep001 out/001-v2.mp4              # 指定输出文件名
npm run render -- ep001 --frames=0-899              # 只导出前 30 秒（每秒 30 帧），快速检查效果
npm run render -- ep001 --scale=0.5                 # 导出一半分辨率（540×960），更快、文件更小，适合发样片
npx remotion still ep001 out/cover.png --frame=60   # 把第 2 秒的画面导出成图片，可以当封面
```

### 其他命令

```powershell
uvx --from edge-tts edge-tts --list-voices | Select-String zh-CN   # 查看所有中文音色
npm run lint                                                       # 检查视频模板代码（改过 src/ 之后用）
```

## 修改视频内容

视频内容都由 `public/episodes/<集数>/storyboard.json` 决定（例如 [001 的分镜](public/episodes/001/storyboard.json)）。改完运行 `npm run voice -- <集数>` 生效。不熟悉 JSON 格式的话，可以直接告诉 AI 助手要改什么，让它来改；格式写错时，脚本会提示错在第几行。

| 想要 | 改哪里 |
| --- | --- |
| 改台词 | 对应分镜的 `lines` |
| 纠正读音（多音字、数字） | `pronunciation`，如 `"221年": "二百二十一年"`。字幕显示原文，配音读替换后的文字。用大模型写分镜时会先自动填上一些，见「[npm run storyboard](#npm-run-storyboard用大模型写分镜)」 |
| 换音色、调语速 | `voice`、`rate`（如 `"+10%"`）。常用音色：`zh-CN-YunyangNeural` 云扬（新闻腔）、`zh-CN-YunxiNeural` 云希、`zh-CN-YunjianNeural` 云健、`zh-CN-XiaoxiaoNeural` 晓晓 |
| 调整句间停顿 | `pauses`（单位：秒）。`line` 是同一画面内两句之间，`scene` 是换图时 |
| 某张图停留太久或太短 | 把 `lines` 拆到新分镜，或合并到相邻分镜。新分镜要起一个新编号（如 `S12b`），并配一张同名图片 |
| 重复使用前面的图 | 加 `"reuse": "S07"`，这个分镜不用再出图 |
| 镜头运动 | `motion`：`zoomIn` `zoomOut` `panLeft` `panRight` `panUp` `panDown`，不写就自动轮换 |
| 背景音乐 | 把音乐文件放进该集的文件夹，设置 `"bgm": {"file": "bgm.mp3", "volume": 0.08}` |
| 改画风 | `imageStyle`，会拼接到每条提示词末尾 |
| 不希望图里出现的东西 | `negativePrompt`，只有支持负面提示词的接口（如千问生图）会用到 |
| 改画面说明、出图提示词 | `visual`、`prompt` |
| 章节卡不读出来，或改成别的读法 | 章节分镜（`"type": "chapter"`）的 `lines`：改成 `[]` 就只显示不读，停留秒数用 `hold` 设置（默认 1.8）；章节卡上显示的文字改 `title` 和 `kicker` |

## API 配置

把项目根目录的 `.env.example` 复制一份，改名为 `.env`，按里面的说明填写。`.env` 只保存在你自己的电脑上，不要把密钥发给别人或贴到聊天里。只有 make、storyboard、images 三个命令会读取 `.env`；预览和导出读取的是 `remotion.env`，不会接触到密钥。

**写分镜的大模型**：任何兼容 OpenAI 协议的服务都可以，`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 三项都要填，例如：

| 服务 | `LLM_BASE_URL` | `LLM_MODEL` |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | `deepseek-flash` |
| 阿里云百炼（千问） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 火山方舟（豆包） | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed-2-1-lite-260915` |

百炼、方舟按量计费的同一个 Key 既能出图，也能写分镜（用方舟 Agent Plan 套餐出图时不一样，见下面的「用订阅套餐出图」）。大模型只决定哪几句话合成一个画面，写画面描述和提示词，再标出容易读错的词；台词原文由脚本保留，不会被改写。

**出图平台**：

| 平台 | `.env` 配置 | 默认模型 |
| --- | --- | --- |
| 阿里云百炼（千问生图 / Z-Image） | `DASHSCOPE_API_KEY`；换模型改 `DASHSCOPE_IMAGE_MODEL` | `z-image-turbo` |
| 火山引擎方舟（Seedream，即梦/豆包同款） | `ARK_API_KEY`，还要在控制台开通对应模型；换模型改 `ARK_IMAGE_MODEL` | `doubao-seedream-5-5-261028` |

两个平台都配置了的话，用 `IMAGE_PROVIDER=bailian` 或 `IMAGE_PROVIDER=ark` 指定默认平台，或者在命令里加 `--provider`。

出图只需要填 Key：两个平台的接口地址（北京地域）已经写在脚本里，模型不填也有默认值。写分镜的大模型可以是任何兼容 OpenAI 协议的服务，所以要填 `LLM_BASE_URL` 告诉脚本用哪家；出图只支持这两个平台，而且两家的接口格式不一样，脚本是分别对接的。要用其他地域（例如百炼新加坡地域 `https://dashscope-intl.aliyuncs.com`）或百炼的业务空间专属域名时，在 `.env` 里加 `DASHSCOPE_BASE_URL` 或 `ARK_BASE_URL`。

**用订阅套餐出图**：

- **方舟 Agent Plan**（包月套餐，Small 档 40 元/月）允许用 API 调用套餐里的 Seedream 出图。在 `.env` 里设置 `ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/plan/v3`，`ARK_API_KEY` 填 Agent Plan 专属 Key，`ARK_IMAGE_MODEL` 填套餐里的模型名（如 `doubao-seedream-5.5`）。
- **怎么扣额度**：出图不按张收费，而是扣套餐的燃料值（AFP）。`doubao-seedream-5.5` 每张 65 AFP，一集 50 多张约 3,500 AFP；Small 档每月 20,000 AFP，每天最多用掉一半。脚本运行前会显示预计消耗多少 AFP，`--max-cost` 只管按张收费的部分。
- **额度用完时**：脚本会停止出图，等额度恢复后重新运行同一条命令就能接着出。如果开启了「超额后付费」，额度用完后会自动转为按量计费。
- **写分镜的大模型不要用套餐**：Agent Plan 里的文本模型不允许用 API 调用，官方规定在 AI 编程工具之外使用可能被判定为滥用，导致订阅停用或封号。所以 `LLM_*` 要用按量计费的地址 `https://ark.cn-beijing.volces.com/api/v3` 和普通 API Key。
- **阿里云百炼的 Token Plan 不能用**：它明确禁止用于批量脚本。百炼请用按量计费的 API Key。

**参考价格**（按量计费；2026 年 11 月从官网查到的价格，按 9:16、约 2K 分辨率计算，以官网为准；审核没通过或生成失败的图不收费）：

| 平台 | 模型 | 元/张 |
| --- | --- | --- |
| 百炼 | `z-image-turbo` | 0.10（开启提示词改写时 0.20）。北京地域开通后 90 天内免费 100 张 |
| 百炼 | `qwen-image-3.0` / `qwen-image-3.0-pro` | 0.18 / 0.25（各免费 10 张）。3.0-pro 的图超过 225 万像素按 0.50 元计费，本项目出图时会自动控制在这以内 |
| 百炼 | `qwen-image-2.1-turbo` / `qwen-image-2.1-pro` | 0.10 / 0.25（各免费 10 张） |
| 百炼 | `qwen-image-2.0` / `qwen-image-2.0-pro` | 0.20 / 0.50 |
| 方舟 | `doubao-seedream-5-5` | 0.13 |
| 方舟 | `doubao-seedream-5-0-flash` / `5-0-lite` / `5-0-pro` | 0.12 / 0.22 / 0.30 |
| 方舟 | `doubao-seedream-4-5` / `4-0` | 0.25 / 0.20 |

一集 50 多张图：用 z-image-turbo 约 5 元，Seedream 5.5 约 7 元，qwen-image-3.0 约 10 元，qwen-image-3.0-pro 约 13 元。写分镜通常只要几分钱。

**怎么选模型**：按百炼官方的说明，`qwen-image-3.0-pro` 是千问的旗舰模型，最擅长在画面里准确写出中英文；`qwen-image-3.0` 兼顾质量和速度；`qwen-image-2.1-turbo` 性价比最高；`z-image-turbo` 是出图快的轻量模型。本项目的画面不需要写字，默认的 z-image-turbo 通常够用。想换模型的话，先用 `npm run images -- 002 --compare z-image-turbo,qwen-image-3.0,qwen-image-3.0-pro` 让每个模型各出 4 张对比（新开通的账号可以用免费额度），选好后在 `.env` 里修改 `DASHSCOPE_IMAGE_MODEL`。

## 相关网址

控制台和账号页面需要先登录。价格、免费额度会变动，以官网为准。

### 阿里云百炼（千问生图 / Z-Image）

| 用途 | 网址 |
| --- | --- |
| 注册阿里云账号 | https://account.aliyun.com/register/qr_register.htm |
| 账号中心（实名认证在这里） | https://account.console.aliyun.com/v2/ |
| 百炼产品介绍 | https://www.aliyun.com/product/bailian |
| 百炼控制台（开通服务、创建 API Key） | https://bailian.console.aliyun.com/ |
| 获取与配置 API Key（文档） | https://help.aliyun.com/zh/model-studio/get-api-key |
| 在线试用 Z-Image（网页里直接出图） | https://bailian.console.aliyun.com/cn-beijing/model/experience/vision/imageGenerate?modelId=z-image-turbo |
| 文生图使用指南（千问、万相、Z-Image，含模型选型） | https://help.aliyun.com/zh/model-studio/text-to-image |
| Z-Image API 文档 | https://help.aliyun.com/zh/model-studio/z-image-api-reference |
| 千问生图 API 文档（3.0、2.1 系列） | https://help.aliyun.com/zh/model-studio/qwen-image-generation-and-editing-api-reference |
| 千问早期生图模型 API 文档（2.0 等） | https://help.aliyun.com/zh/model-studio/qwen-image-api |
| 文生图提示词指南 | https://help.aliyun.com/zh/model-studio/text-to-image-prompt |
| 模型价格 | https://help.aliyun.com/zh/model-studio/model-pricing |
| 新人免费额度、「用完即停」开关 | https://help.aliyun.com/zh/model-studio/new-free-quota |
| 限流说明 | https://help.aliyun.com/zh/model-studio/rate-limit |
| 错误码 | https://help.aliyun.com/zh/model-studio/error-code |
| Token Plan 常见问题（含不能用于批量脚本的规定） | https://help.aliyun.com/zh/model-studio/token-plan-faq |
| 用量监控 | https://bailian.console.aliyun.com/cn-beijing/model/telemetry |
| 账单查询、停止计费 | https://help.aliyun.com/zh/model-studio/bill-query-and-cost-management |
| 用 OpenAI 协议调用千问（写分镜） | https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope |
| 万相网页版（手动出图） | https://tongyi.aliyun.com/wan |

### 火山引擎方舟（Seedream，即梦/豆包同款）

| 用途 | 网址 |
| --- | --- |
| 注册火山引擎账号 | https://signin.volcengine.com/auth/signup |
| 实名认证 | https://console.volcengine.com/user/authentication/ |
| 方舟产品介绍 | https://www.volcengine.com/product/ark |
| 方舟控制台 | https://console.volcengine.com/ark |
| 开通模型（Seedream 要先开通才能调用） | https://ark.volcengine.com/region:cn-beijing/openManagement |
| 创建 API Key | https://ark.volcengine.com/region:cn-beijing/apiKey |
| 图片生成 API 文档 | https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh |
| Seedream 提示词指南 | https://ark.volcengine.com/region:cn-beijing/docs/seedream-4-0-5-0-prompt-guide |
| 模型列表（查模型 ID） | https://docs.volcengine.com/docs/ark/model-list?lang=zh |
| 模型价格 | https://docs.volcengine.com/docs/ark/model-pricing?lang=zh |
| 定价详情 | https://www.volcengine.com/pricing?product=ark_bd&tab=1 |
| 价格计算器 | https://www.volcengine.com/pricing?product=ark_bd&tab=2 |
| Base URL 和鉴权说明 | https://ark.volcengine.com/region:cn-beijing/docs/base-url-and-authentication |
| 对话 API（用豆包写分镜） | https://ark.volcengine.com/region:cn-beijing/docs/chat-api |
| Agent Plan 套餐介绍、订阅 | https://www.volcengine.com/activity/agentplan |
| Agent Plan 套餐概览（额度、限额、使用限制） | https://docs.volcengine.com/docs/ark/agent-plan-personal-plan-overview?lang=zh |
| Agent Plan 燃料值（AFP）抵扣规则 | https://docs.volcengine.com/docs/ark/agent-plan-personal-afp-credits-billing-rules?lang=zh |
| Agent Plan 用 API 出图（专属地址和 Key） | https://docs.volcengine.com/docs/ark/agent-plan-personal-visual-models?lang=zh |
| 错误码 | https://docs.volcengine.com/docs/ark/error-codes?lang=zh |
| 即梦网页版（手动出图） | https://jimeng.jianying.com/ |
| 豆包网页版 | https://www.doubao.com/ |

### DeepSeek（写分镜）

| 用途 | 网址 |
| --- | --- |
| 创建 API Key | https://platform.deepseek.com/api_keys |
| API 文档 | https://api-docs.deepseek.com/zh-cn/ |
| 模型和价格 | https://api-docs.deepseek.com/zh-cn/quick_start/pricing |

## 项目文件

| 路径 | 说明 |
| --- | --- |
| `<集数>.标题——副标题.md` | 文案，放在项目根目录 |
| `public/episodes/<集数>/storyboard.json` | 分镜：台词分组、画面描述、提示词、音色等，修改视频内容就改这里 |
| `public/episodes/<集数>/images/` | 图片，按分镜编号命名；`_generated.json` 记录每张图是怎么生成的 |
| `public/episodes/<集数>/compare/` | 不同平台、模型的出图对比（`--compare` 生成），选定后可以删掉 |
| `public/episodes/<集数>/` 里的其他文件 | `narration.wav`（配音）、`timeline.json`（时间线）、`captions.srt`（字幕）、`prompts.md`（出图提示词），都是自动生成的，不要手改 |
| `out/` | 导出的成片 |
| `.env.example`、`.env` | API Key 配置模板，以及你自己填好的配置（不要发给别人） |
| `remotion.env` | 预览和导出时读取的环境变量文件，保持为空 |
| `scripts/` | 各命令的脚本：`make_video.py` 一键生成，`gen_storyboard.py` 写分镜，`build_episode.py` 配音和时间线，`gen_images.py` 出图 |
| `src/` | Remotion 视频模板：标题、章节卡、字幕、转场、推拉镜头 |
| `public/fonts/` | 思源黑体、思源宋体（SIL OFL 协议，可免费商用） |

## 常见问题

**换一台电脑怎么用？** 复制项目文件夹，删掉副本里的 `node_modules`（约 700 MB，到新电脑上重新安装即可）和 `out`（导出的成片，需要的话单独拷贝），然后在新电脑上按「[准备环境](#1-准备环境每台电脑只做一次)」安装工具、运行 `npm install`。`.env` 里是你的密钥，发给别人之前记得删掉。`.cache` 是配音缓存，可带可不带，不带的话会重新合成，结果完全相同。

**第一次运行失败？** 先重试一次。还是卡在下载 Python 的话，运行 `winget install Python.Python.3.13` 后再试。新开的终端提示找不到 `node`，重启 VS Code 即可。

**一键生成后有几个画面是重复的？** 那些分镜的图片没能生成（通常是没通过内容审核），暂时用了相邻画面，运行结束时会列出编号。修改它们的 `prompt` 后，运行 `npm run images -- 002 --only 编号`，再运行 `npm run render -- ep002`。

**想换个平台或画风，把图全部重画？** 改好 `imageStyle` 或选好平台后，运行 `npm run images -- 002 --force`（加 `--provider` 指定平台）。所有图都会重新生成、重新收费。

**想做历史以外的题材？** 默认的画风、音色和分镜提示词都是按历史题材调的，换题材时建议改三处：

- **画风**：默认是中国风厚涂。先运行 `npm run storyboard -- 002` 写分镜，把 storyboard.json 里的 `imageStyle` 改成适合题材的画风（比如儿童故事用水彩绘本风，知识科普用扁平插画），再运行 `npm run make -- 002` 出图、导出。整个系列都要换的话，改 `scripts/build_episode.py` 里的 `DEFAULT_STYLE`，之后新写的分镜都会用它。
- **音色**：默认的云扬是新闻腔，讲故事、情感类可以换成晓晓（`zh-CN-XiaoxiaoNeural`）或云希（`zh-CN-YunxiNeural`）。新写分镜时加 `--voice`；已经有分镜的，改 storyboard.json 里的 `voice`，再运行 `npm run voice -- 002`。
- **分镜提示词**：`scripts/gen_storyboard.py` 开头的 `SYSTEM_PROMPT` 要求服饰、建筑、器物符合历史时期，举的例子也是新石器时代。可以让 AI 助手改成对应题材的要求和例子，写出来的出图提示词会更贴题。

**公司网络设置了代理？** 脚本会自动使用系统代理（`HTTP_PROXY` / `HTTPS_PROXY` 环境变量）。

**出图很慢？** 生成一张图通常只要 10–20 秒，慢一般是慢在下载：百炼只返回 PNG，每张约 3 MB；方舟返回 JPEG，每张约 0.5 MB。在一个经公司代理、下载只有约 60 KB/s 的网络里实测，百炼每张图下载要 30–60 秒，方舟只要 3–9 秒。下载中途断开会自动续传，不用管。

**有独立显卡（NVIDIA）会更快吗？** 快不了多少。写分镜、配音、出图都在云端完成，和本机显卡无关；只有最后的导出在本机进行，而导出主要靠 CPU。在 i5-12500 + 核显的电脑上实测：导出 30 秒视频约 45 秒，其中视频编码约占四分之一；让核显参与画面绘制（`--gl=angle`）没有变快。有 NVIDIA 显卡（驱动 525 以上）时，可以让显卡负责编码，导出最多快四分之一左右：

```powershell
npm run render -- ep002 --hardware-acceleration=if-possible --video-bitrate=10M
```

没有 NVIDIA 显卡的电脑不要加这两个参数：实测 Remotion 仍会选用 NVIDIA 编码器，导致导出失败。一键生成（make）导出时不使用显卡编码。显卡更大的用处是在本机运行开源生图模型（例如用 ComfyUI 运行 Z-Image），这样出图就不用按张付费，但需要另外搭建环境。

**想换成付费配音或真人录音？** 需要改 `scripts/build_episode.py` 里的配音部分；用真人录音的话，字幕时间可以改用 Whisper 语音识别生成。

## 注意事项

- 配音用的是 edge-tts：它调用微软 Edge「大声朗读」的在线服务，背后是微软的 AI 语音模型（不是大模型）。免费、不用密钥，但需要联网，文案会发送给微软；它不是官方开放接口，以后可能失效。
- 使用大模型、生图 API 时，文案和提示词会发送给对应的平台，平台会做内容审核。
- API Key 只能放在 `.env`，不要写进 `remotion.env`。Remotion 默认会把 `.env` 里的所有内容写进预览页面，而预览服务也会监听局域网地址，所以本项目让预览和导出改为读取 `remotion.env`。
- 本项目的 `.npmrc` 使用 npmmirror 国内镜像。
- 配音会自动做响度统一，成片约 -15 LUFS，并给峰值留了余量，适合短视频平台。
- 发布前请自查：AI 图片里的朝代服饰、器物是否穿越；背景音乐有没有使用授权。
- 图片和配音都是 AI 生成的，发布时要按平台要求主动声明。
- Remotion 对个人和 3 人以内的公司免费，更大的团队需要购买授权，见 [remotion.pro/license](https://www.remotion.pro/license)。
