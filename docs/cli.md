# 命令行制作视频

网页版（`npm run web`）能做的，命令行都能做，网页上的每个操作也都是在后台运行这些命令。下面这些只有命令行能做：对比不同生图平台或模型的效果、只导出一段或半分辨率的样片、硬件加速导出、在 Remotion 里逐帧预览，以及直接改 `storyboard.json` 里网页上没有入口的设置（停顿、背景音乐、复用前面的图片等）。

网页和命令行用的是同一套文件（`texts/`、`public/episodes/`、`out/`），可以混着用。准备环境、填写 API Key 见 [README](../README.md#快速开始)，文案的写法见「[文案怎么写](../README.md#文案怎么写)」。命令行不会检查 uv 和 FFmpeg 装没装：运行一次 `npm run web` 按提示装好，或者按 README 里的命令自己装。

所有命令在项目文件夹里运行。**传给脚本的参数要写在 `--` 后面**，例如 `npm run images -- 001 --pilot`，否则参数会被 npm 拿走。

## 一键生成

把文案放进项目根目录的 `texts/` 文件夹，文件名以集数编号开头，例如 `texts/002.《负荆请罪》.md`（`——` 前面是标题，后面是副标题，都显示在视频开头）。然后运行：

```powershell
npm run make -- 002
```

大模型写分镜 → 配音 → 出图 → 导出，成片在 `out/002.mp4`，封面在 `out/002-cover.jpg`。7 分钟左右的视频大约要 15–30 分钟，出图约 5–10 元。中途断了重新运行同一条命令即可，做完的部分不会重做、不会重复花钱。

## 分步制作

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

网页版的启动参数（`npm run web`）见 [README](../README.md#2-启动网页)。

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
| `--fill-missing` | 还没有图片的分镜暂时用相邻画面的图片，和 make 导出前一样（网页版导出时用） |
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

台词、读音、音色语速、画风、角色外貌、画面说明、出图提示词、镜头运动、画面里的角色，在网页上就能改；下表里停顿、复用图片、背景音乐、`negativePrompt`、`follow`、章节卡这几项，网页上还没有入口，要直接改这个文件。

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

## 常见问题

**一键生成后有几个画面重复？** 那几张图没生成出来（通常是审核没过），暂时用了相邻画面。改好它们的 `prompt` 后运行 `npm run images -- 002 --only 编号`，再运行 `npm run render -- ep002`。

**以前写的分镜，人物前后不一致？** 角色表是新写分镜时才有的。用 `npm run storyboard -- 002 --force` 重写分镜，再用 `npm run images -- 002 --force` 全部重画（分镜编号会重排，会重新收费）。只想换画风的话，用 `--style`。

**想少出几张图？** 新写分镜时加 `--images`，如 `npm run make -- 002 --images 20`。已有分镜的要先运行 `npm run storyboard -- 002 --force --images 20`，原来的图片对不上，要重画。

**换音色？** 新写分镜时加 `--voice`，已有分镜改 storyboard.json 的 `voice`。

**独立显卡能加快导出吗？** 基本不能：分镜、配音、出图都在云端，只有导出在本机，主要靠 CPU。有 NVIDIA 显卡（驱动 525 以上）时，`npm run render -- ep002 --hardware-acceleration=if-possible --video-bitrate=10M` 最多快四分之一左右；没有 NVIDIA 显卡不要加，会导出失败。
