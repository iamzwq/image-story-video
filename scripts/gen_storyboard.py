# /// script
# requires-python = ">=3.10"
# dependencies = ["edge-tts>=7.2", "pypinyin>=0.55"]
# ///
"""用大模型把口播文案写成分镜（storyboard.json），然后自动配音、生成时间线和出图提示词。

    npm run storyboard -- 002            读取 texts/ 里以 002 开头的 .md 文案
    npm run storyboard -- 002 --force    已有分镜时重新生成（旧文件备份为 storyboard.bak.json）
    npm run storyboard -- 002 --images 20    整集只用 20 张图，每张图对应一段较长的台词
    npm run storyboard -- 002 --style    给已有的分镜按内容重新推荐画风（只改 imageStyle）

大模型在 .env 里配置（LLM_BASE_URL / LLM_API_KEY / LLM_MODEL），任何兼容 OpenAI 协议的服务都可以。
模型先按内容推荐画风、定角色表（反复出现的人物和他们固定的外貌），再决定「哪几句合成一个画面」和每个画面的描述、提示词，
并标出容易读错的词和带数字的说法（写进 pronunciation，只影响配音）；台词原文由脚本保留，不会被改写。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from pypinyin import Style, lazy_pinyin, pinyin
from pypinyin.contrib.tone_convert import to_tone3

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_episode as be  # noqa: E402
from api_common import ApiError, LLMError, chat, llm_settings, missing_llm_vars  # noqa: E402
from envfile import env, load_env  # noqa: E402

MOTIONS = {"zoomIn", "zoomOut", "panLeft", "panRight", "panUp", "panDown"}
CHUNK_LINES = 24  # 每次请求最多发送的句子数，长章节会拆成几次
CHUNK_GROUPS = 12  # 限定张数（--images）时，一段的组数超过这个数才拆成几次请求
MAX_CAST = 12  # 角色表最多几个角色
HANZI_RE = re.compile(r"[\u3007\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0003134f]+")
# 核对数字念法时用：汉字数字和单位
CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "幺": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000}
CN_BIG = {"万": 10_000, "亿": 100_000_000}
CN_NUMBER_RE = re.compile("[零〇一幺二两三四五六七八九十百千万亿]+")

PRONOUNCE_PROMPT = """你是播音审校，负责找出语音合成（TTS）容易读错的地方，写出正确的念法。替换只影响配音，字幕仍显示原文。

要列出两类：
一、容易读错的汉字词，只挑真正容易读错的：
1. 多音字在文中读的不是最常用的音，例如「禅让」的禅读 shàn。
2. 生僻字，以及读法特殊的古代人名、地名、官职、族名，例如「单于」读 chán yú、「冒顿」读 mò dú。
常用词、按常用读音就能读对的词都不要列，宁缺毋滥。
二、文中所有带阿拉伯数字的说法，都写成配音要念的汉字，免得 TTS 按符号乱念：
- 年份按习惯念：四位数逐位念，如「1949年」念「一九四九年」；三位数及以下按数值念，如「公元前221年」念「公元前二百二十一年」。
- 其他按口语念，例如「10%」念「百分之十」，「1/3」念「三分之一」，「3-5年」念「三到五年」，「8:30」念「八点三十」，「2个」念「两个」。
两类都没有就输出空列表。

每一项的字段：
- word：原文里的词或说法，必须与原文一字不差。汉字词至少两个字；数字要连同紧挨着的单位、符号一起写，如「221年」「10%」「3-5年」，不能只截取一个数的一部分。替换会作用到全文所有出现这个词的地方，所以它在每一处的念法都必须相同，做不到就换成更长的说法。
- pinyin：汉字词在文中的正确读音，用带声调符号的拼音，音节之间用空格隔开；数字的说法不用写，留空。
- say：替换文字，只用汉字。汉字词：读音与 pinyin 完全相同（包括声调），字数与 word 相同，尽量选只有一个读音的常用字，原本就能读对的字保留不变。数字的说法：写出配音要念的全部汉字，原文里的汉字原样保留。

只输出 JSON，不要输出解释，格式：
{"words":[{"word":"单于","pinyin":"chán yú","say":"蝉于"},{"word":"公元前221年","pinyin":"","say":"公元前二百二十一年"}]}"""

STYLE_PROMPT = """你是短视频的美术指导。下面是一期短视频的完整文案，视频由几十张 AI 插画配上配音和字幕组成。请根据文案的题材、时代、地域、受众和情绪基调，给整集定一个统一的插画风格。

要求：
1. 先读懂这期内容讲的是什么、给谁看、想营造什么情绪，再推荐最能烘托它的画风。不必拘泥于常见的风格，可以自由组合绘画媒介、技法和色彩。
2. name：画风名称，2–8 个字。
3. style：画风描述，40–80 字，写清楚绘画媒介和技法、线条笔触、主色调、质感和光线氛围，让几十张图看起来是同一套作品。用具体、能画出来的词，不要堆砌空泛的形容词。只写怎么画，不写画什么：不写具体的人物、场景、构图和画面比例。
4. 不要写具体画家、动画公司或作品的名字，也不要选漫画分格、海报、信息图这类容易画出文字和边框的形式。

只输出 JSON，不要输出解释，格式：
{"name":"……","style":"……"}"""

CAST_PROMPT = """你是连环画的人物设计师。下面是一期短视频的完整文案，视频由几十张插画依次组成。为了让同一个人物在不同画面里长得一样，请列出需要在多个画面里出现的人物，给每个人物定一份固定的外貌设定。

要求：
1. 只列需要在两个以上画面里画出来的具体人物：有名有姓的人物（如秦始皇、魏忠贤），以及贯穿一段内容的类型人物（如某个朝代的皇帝、某个藩镇的节度使）。文案泛泛讲道理时反复出现的类型人物（如泛指的「皇帝」），也可以设定一个固定形象。只出现一次的人物，以及群臣、士兵、百姓这类群像不要列。通常 3–10 个，没有就输出空列表。
2. 同一个称呼在文中指不同时代的不同人时（例如先讲东汉的皇帝，后讲明朝的皇帝），要拆成不同的角色，名字里写明时代或身份，例如「东汉少年皇帝」「明熹宗」。
3. name：角色名，2–8 个字，不能重复。分镜提示词会直接用这个名字指代人物。
4. look：外貌设定，40–80 字，只写看得见、而且在各个画面里都不变的特征：性别、年龄段、脸型五官、发型胡须、体型，以及服饰的款式、主色和标志性配饰。服饰要符合人物所处的历史时期。不写动作、表情、场景和画风。
5. 各角色的年龄、体型和服饰主色要有明显区别，一眼能分清。

只输出 JSON，不要输出解释，格式：
{"cast":[{"name":"东汉少年皇帝","look":"……"}]}"""

COMIC_RULES = """连环画规则（整集的画面要像一本连环画，前后连贯）：
1. 角色表里的人物出场时，prompt 里直接写角色名，不要再写他的长相和服饰（出图时会按角色表统一补上），例如「东汉少年皇帝端坐御座」。角色表以外的人物（群臣、士兵、百姓等）照常描述。
2. 同一段落里，台词没有明确换时代、地点或时间时，沿用上一个画面的地点、陈设和光线，不要每个画面换一种时段和光线。
3. 景别要有变化：交代环境用远景、全景，表现人物动作用中景，表现神态、手部动作或关键器物用近景、特写，不要连续几个画面都是大殿全景。
4. 每个画面只画一个时间、一个地点的连贯场景，不要分格、拼贴，也不要把不同时间、地点的场景拼进同一个画面。"""

SYSTEM_PROMPT = """你是短视频分镜师，负责把口播文案拆成画面。视频形式是「AI 配音 + 静态插画 + 字幕」，每个画面是一张 AI 生成的插画，播放时镜头会缓慢推拉。

任务：把编号的句子按顺序分组，每组对应一个画面，并为每个画面写画面说明和出图提示词。

分组规则：
1. 只能把相邻的句子分在一组，按顺序覆盖全部句子，不能遗漏、重复或打乱。
2. 每组总时长尽量在 5–10 秒，最长不超过 13 秒；话题转折的地方换画面。
3. 一句话不能拆开。

""" + COMIC_RULES + """

每个画面的字段：
- from、to：这组起止句子的编号（包含两端）。
- visual：画面说明，不超过 10 个字。
- prompt：中文出图提示词，40–90 字，只描述画面内容：主体、动作、场景、时代细节（服饰、建筑、器物要符合对应的历史时期）、景别构图、光线氛围。不要写画风和画面比例（会统一追加）。画面里不能出现文字、字母、标语、牌匾、印章；台词里的抽象概念要转化成具体可见的场景、人物动作或象征物。
- cast：画面里出现的角色表人物的名字，没有就写 []。
- follow（可选）：这个画面和上一个画面发生在同一地点、同一时间，像连环画的下一格时写 true，出图时会参考上一格的场景和光线；换了地点或时间就不写。列表的第一个画面，只有给出了「上一个画面」时才能写 follow。
- motion：镜头运动，从 zoomIn、zoomOut、panLeft、panRight、panUp、panDown 中选一个：大场面、俯瞰宜 zoomOut 或平移，人物和细节宜 zoomIn，高耸的事物或上下层级宜 panUp。
- reuse（可选）：只有在明确回顾前面已经出现过的内容时，才填「已有画面」里的编号，这时可以不写 prompt。

只输出 JSON，不要输出解释，格式：
{"scenes":[{"from":1,"to":2,"visual":"……","prompt":"……","cast":["……"],"motion":"zoomIn"},{"from":3,"to":3,"visual":"……","prompt":"……","cast":[],"follow":true,"motion":"panLeft"},{"from":4,"to":4,"visual":"……","reuse":"S05","motion":"panLeft"}]}

示例（另一期视频的片段，角色表里有秦始皇、李斯）：
1. [5.4s] 公元前221年，秦国灭掉了最后一个对手齐国，统一了天下。
2. [4.4s] 秦王嬴政觉得，自己的功业超过了传说中的三皇五帝，
3. [3.0s] 于是给自己定了一个新称号：皇帝。
4. [5.2s] 丞相李斯建议，不再分封诸侯，而是把全国分成郡县，由朝廷直接派官管理。
5. [2.8s] 秦始皇当场拍板同意。
输出：
{"scenes":[{"from":1,"to":1,"visual":"秦灭齐国","prompt":"战国末年的齐国都城临淄城外，黑色旌旗的秦军方阵开进洞开的城门，城头的齐军放下兵器，尘土飞扬，阴沉的天光，大远景俯瞰","cast":[],"motion":"zoomOut"},{"from":2,"to":3,"visual":"始皇帝称号","prompt":"咸阳宫大殿内，秦始皇站在高台御座前，俯视台阶下跪拜的群臣，玄色帷幕高垂，青铜灯树燃着烛火，仰拍全景，暖色烛光与深色阴影","cast":["秦始皇"],"motion":"panUp"},{"from":4,"to":5,"visual":"李斯献策","prompt":"咸阳宫大殿的御座前，李斯躬身捧着竹简进言，秦始皇在御座上抬手示意，两人近景，烛光映在脸上","cast":["秦始皇","李斯"],"follow":true,"motion":"zoomIn"}]}"""

# 用 --images 限定整集图片张数时，追加在 SYSTEM_PROMPT 后面
FIXED_COUNT_NOTE = """

本视频限定了图片张数，下面两条代替上面关于每组时长和 prompt 字数的要求：
- 必须正好分成用户要求的组数，各组时长尽量接近，在话题转折的地方换画面，不受 5–10 秒的限制；不要用 reuse。
- 每组台词较长，prompt 写 60–120 字：选这组台词里最核心、最有代表性的场景来画，可以包含两三个相关的元素，但只画一个连贯的场景，不要拼贴、分格或画成多个小画面。"""


class PlanError(Exception):
    pass


def require_llm() -> tuple[str, str, str]:
    settings = llm_settings()
    if settings is None:
        be.die(
            f"还没有配置大模型：请在 .env 里填写 {'、'.join(missing_llm_vars())}（参考 .env.example）。\n"
            "  不想配置的话，也可以直接让 AI 助手帮你写分镜，或运行 npm run voice 生成按时长分组的草稿。"
        )
    return settings


def ask(settings: tuple[str, str, str], messages: list[dict]) -> str:
    try:
        return chat(settings, messages)
    except LLMError as err:
        raise PlanError(str(err)) from None
    except ApiError as err:
        be.die(f"调用大模型失败：{err}")
        raise


def extract_json(content: str):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
    try:
        return json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                pass
    raise PlanError("输出的不是合法 JSON")


def ask_json(cfg, system: str, user: str, check: Callable):
    """让大模型输出 JSON，交给 check 校验并返回 check 的结果。不合格时把问题告诉模型再试一次，两次都不行就抛出 PlanError。"""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    error = PlanError("没有结果")
    for _ in range(2):
        content = ""
        try:
            content = ask(cfg, messages)
            return check(extract_json(content))
        except PlanError as err:
            error = err
            if content:
                messages += [{"role": "assistant", "content": content},
                             {"role": "user", "content": f"上面的输出有问题：{err}。请按要求重新输出完整的 JSON。"}]
    raise error


def picked_cast(value, cast: dict[str, str] | None) -> list[str]:
    """模型填的 cast：只保留角色表里有的名字，去重。"""
    names = value if isinstance(value, list) else []
    return [n for n in dict.fromkeys(str(x).strip() for x in names) if n in (cast or {})]


def is_true(value) -> bool:
    return value is True or str(value).strip().lower() == "true"


def check_groups(obj, n: int, known: set[str], cast: dict[str, str] | None = None) -> list[dict]:
    groups = obj.get("scenes") if isinstance(obj, dict) else obj
    if not isinstance(groups, list) or not groups:
        raise PlanError("没有 scenes 数组")
    out, expected = [], 1
    for g in groups:
        if not isinstance(g, dict):
            raise PlanError("scenes 里的每一项都必须是对象")
        try:
            start, end = int(g.get("from")), int(g.get("to"))
        except (TypeError, ValueError):
            raise PlanError("每个画面都要有整数的 from 和 to") from None
        if start != expected:
            raise PlanError(f"第 {expected} 句没有被分组，或者分组重叠、顺序不对（某组从第 {start} 句开始）")
        if end < start or end > n:
            raise PlanError(f"分组 {start}–{end} 超出了句子范围 1–{n}")
        reuse = str(g.get("reuse") or "").strip()
        if reuse and reuse not in known:
            reuse = ""
        prompt = str(g.get("prompt") or "").strip()
        if not reuse and not prompt:
            raise PlanError(f"第 {start}–{end} 句的画面缺少 prompt")
        motion = g.get("motion") if g.get("motion") in MOTIONS else None
        out.append({"from": start, "to": end, "visual": str(g.get("visual") or "").strip()[:16],
                    "prompt": prompt, "reuse": reuse, "motion": motion,
                    "cast": [] if reuse else picked_cast(g.get("cast"), cast),
                    "follow": not reuse and is_true(g.get("follow"))})
        expected = end + 1
    if expected != n + 1:
        raise PlanError(f"第 {expected}–{n} 句没有被分组")
    return out


def fallback_groups(lines: list[tuple[str, float]], count: int | None = None) -> list[dict]:
    durations = [d for _, d in lines]
    spans = be.even_groups(durations, count) if count else be.time_groups(durations)
    return [{"from": a, "to": b, "visual": "", "prompt": "", "reuse": "", "motion": None, "cast": [], "follow": False}
            for a, b in spans]


def cast_listing(cast: dict[str, str]) -> str:
    if not cast:
        return "角色表：无（cast 都写 []）"
    return "角色表（prompt 里用这些名字指代人物，cast 只能填这些名字）：\n" + "\n".join(f"- {n}：{look}" for n, look in cast.items())


def plan_chunk(cfg, ctx: str, section: str, lines: list[tuple[str, float]], known: list[tuple[str, str]],
               warnings: list[str], count: int | None = None, cast: dict[str, str] | None = None,
               prev: dict | None = None) -> list[dict]:
    """让大模型给一段句子分组、写提示词；count 不为空时必须正好分成 count 组。
    prev 是本段里紧挨着这些句子的上一个画面，模型据此判断第一个画面能不能 follow。"""
    listing = "\n".join(f"{i}. [{d:.1f}s] {t}" for i, (t, d) in enumerate(lines, 1))
    existing = "，".join(f"{sid} {vis}" for sid, vis in known) or "无"
    task = f"请把下面 {len(lines)} 句正好分成 {count} 组" if count else f"请为下面 {len(lines)} 句分组"
    prev_line = f"上一个画面：{prev.get('visual', '')}：{prev['prompt']}\n" if prev and prev.get("prompt") else ""
    user = (f"{ctx}\n\n{cast_listing(cast or {})}\n\n当前段落：{section}\n已有画面（可以复用）：{existing}\n{prev_line}\n"
            f"{task}（编号只在本段内有效）：\n{listing}")
    system = SYSTEM_PROMPT + FIXED_COUNT_NOTE if count else SYSTEM_PROMPT

    def check(obj) -> list[dict]:
        groups = check_groups(obj, len(lines), {sid for sid, _ in known}, cast)
        if count and len(groups) != count:
            raise PlanError(f"要求正好分成 {count} 组，实际分成了 {len(groups)} 组")
        return groups

    try:
        return ask_json(cfg, system, user, check)
    except PlanError as err:
        last_error = str(err)
    if len(lines) > 4 and count != 1:
        half = len(lines) // 2
        first, second = lines[:half], lines[half:]
        n1, n2 = be.allocate_images(count, [[d for _, d in first], [d for _, d in second]]) if count else (None, None)
        head = plan_chunk(cfg, ctx, section, first, known, warnings, n1, cast, prev)
        tail = plan_chunk(cfg, ctx, section, second, known, warnings, n2, cast, head[-1] if head else prev)
        return head + [{**g, "from": g["from"] + half, "to": g["to"] + half} for g in tail]
    warnings.append(f"「{section}」有 {len(lines)} 句没能让模型分好（{last_error}），已按时长自动分组，提示词需要补写")
    return fallback_groups(lines, count)


def chunk_section(lines: list[tuple[str, float]], want: int | None) -> list[tuple[list[tuple[str, float]], int | None]]:
    """把一段的句子切成几次请求，返回 [(句子, 这次要分成的组数)]。
    want 是这一段限定的画面数（--images），为空时不限定，每次最多 CHUNK_LINES 句；
    限定时组数少，整段一起发给模型才能把各组时长分匀，只在组数超过 CHUNK_GROUPS 时才拆开。"""
    parts = math.ceil(len(lines) / CHUNK_LINES) if want is None else math.ceil(want / CHUNK_GROUPS)
    size = math.ceil(len(lines) / parts)
    chunks = [c for c in (lines[k * size:(k + 1) * size] for k in range(parts)) if c]
    counts = be.allocate_images(want, [[d for _, d in c] for c in chunks]) if want is not None else [None] * len(chunks)
    return list(zip(chunks, counts))


def syllables(text: str) -> list[str]:
    """把拼音拆成音节，统一写成 chan2 这样的数字声调，轻声记为 5。"""
    return [to_tone3(s, neutral_tone_with_five=True) for s in re.split(r"[\s'’-]+", text.lower()) if s]


def same_sound(a: str, b: str) -> bool:
    """两个音节是否同音。词典对轻声的标法不统一，所以轻声和任何声调都算相同。"""
    ma, mb = re.fullmatch(r"([a-z]+)([1-5])", a), re.fullmatch(r"([a-z]+)([1-5])", b)
    return bool(ma and mb) and ma[1] == mb[1] and (ma[2] == mb[2] or "5" in (ma[2], mb[2]))


def cn_value(run: str) -> int:
    """汉字数字的数值：二百二十一 → 221；没有十、百、千、万、亿这些单位时按逐位念法算，一九四九 → 1949。"""
    if not any(c in CN_UNITS or c in CN_BIG for c in run):
        return int("".join(str(CN_DIGITS[c]) for c in run))
    total = section = number = 0
    for c in run:
        if c in CN_DIGITS:
            number = CN_DIGITS[c]
        elif c in CN_UNITS:
            section += (number or 1) * CN_UNITS[c]
            number = 0
        else:
            section += number
            total = (total + section) * CN_BIG[c] if c == "亿" else total + section * CN_BIG[c]
            section = number = 0
    return total + section + number


def number_reading_ok(word: str, say: str) -> bool:
    """核对数字说法的念法：原文里的汉字要按顺序原样保留，念出来的数要和原文的阿拉伯数字一一对得上。
    例如 公元前221年 → 公元前二百二十一年、1.5万人 → 一点五万人、3-5年 → 三到五年、10% → 百分之十。"""
    pieces, pos = [], 0
    for seg in HANZI_RE.findall(re.sub(r"\d+", " ", word)):
        i = say.find(seg, pos)
        if i < 0:
            return False
        pieces.append(say[pos:i])
        pos = i + len(seg)
    pieces.append(say[pos:])
    spoken = re.sub("[百千万]分之", "、", "、".join(pieces))  # 百分之十 里的「百」不是数
    want = sorted(int(d) for d in re.findall(r"\d+", word))
    return want == sorted(cn_value(run) for run in CN_NUMBER_RE.findall(spoken))


def number_isolated(word: str, text: str) -> bool:
    """数字说法在原文的每一处都不能紧挨着别的数字，否则替换会把一个数拆开（比如用 21年 去替换 221年 里的一段）。"""
    for m in re.finditer(re.escape(word), text):
        before = text[m.start() - 1] if m.start() else ""
        after = text[m.end()] if m.end() < len(text) else ""
        if (word[0].isdigit() and (before.isdigit() or before == ".")) or (
                word[-1].isdigit() and (after.isdigit() or after in ".%")):
            return False
    return True


def check_number(word: str, say: str, text: str) -> str | None:
    """检查一个带阿拉伯数字的说法，能用时返回 None，否则返回不采用的原因。"""
    if not HANZI_RE.fullmatch(say):
        return f"{word}→{say}：念法只能用汉字"
    if not number_isolated(word, text):
        return f"{word}：原文里它是更长数字的一部分，替换会把数字拆开，要连同前后的数字一起写"
    if word.isdigit() and text.count(word) > 1:
        return f"{word}：光是数字、在文中出现了好几次，各处念法可能不同，要连同单位一起写（如 {word}年）"
    if not number_reading_ok(word, say):
        return f"{word}→{say}：念出来的数和原文对不上，或者改动了原文里的字"
    return None


def check_pronunciation(obj, text: str) -> tuple[list[tuple[str, str, str]], list[str]]:
    """检查模型标出的读音，返回 ([(原词, 替换文字, 拼音)], 没有采用的说明)。
    汉字词：拼音要是字典里这几个字的读音之一，同音字的读音要和拼音一致，防止模型选错字、标错声调。
    带数字的说法：念出来的数要和原文对得上（拼音为空）。"""
    items = obj.get("words") if isinstance(obj, dict) else obj
    if not isinstance(items, list):
        raise PlanError("没有 words 数组")
    accepted: list[tuple[str, str, str]] = []
    rejected: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        word, say = str(item.get("word") or "").strip(), str(item.get("say") or "").strip()
        py = " ".join(str(item.get("pinyin") or "").split())
        if not word or not say or word not in text or any(w == word for w, _, _ in accepted):
            continue
        if any(ch.isdigit() for ch in word):
            reason = check_number(word, say, text)
            if reason:
                rejected.append(reason)
            else:
                accepted.append((word, say, ""))
            continue
        if len(word) < 2 or not HANZI_RE.fullmatch(word) or say == word or len(say) != len(word) or not HANZI_RE.fullmatch(say):
            continue
        want = syllables(py)
        readings = [pinyin(ch, style=Style.TONE3, heteronym=True, neutral_tone_with_five=True)[0] for ch in word]
        if len(want) != len(word) or not all(
                r == [ch] or any(same_sound(w, x) for x in r) for ch, w, r in zip(word, want, readings)):
            rejected.append(f"{word}（{py or '没有拼音'}）：拼音和字典里这几个字的读音对不上")
            continue
        if not all(same_sound(w, g) for w, g in zip(want, lazy_pinyin(say, style=Style.TONE3, neutral_tone_with_five=True))):
            rejected.append(f"{word}→{say}：「{say}」读 {' '.join(lazy_pinyin(say, style=Style.TONE))}，不是 {py}")
            continue
        accepted.append((word, say, py))
    return accepted, rejected


def find_pronunciation(cfg, heading: str, text: str, warnings: list[str]) -> dict[str, str]:
    """让大模型标出容易读错的词和带数字的说法，返回写进 pronunciation 的 {原文: 配音念的文字}。"""
    print(f"正在用 {env('LLM_MODEL')} 找出容易读错的词和数字…")
    try:
        accepted, rejected = ask_json(cfg, PRONOUNCE_PROMPT, f"视频标题：{heading}\n\n文案：\n{text}",
                                      lambda obj: check_pronunciation(obj, text))
    except PlanError as err:
        warnings.append(f"没能让模型标出容易读错的词（{err}），pronunciation 是空的，需要的话自己补")
        return {}
    if accepted:
        print("  配音时改读（字幕仍显示原文）："
              + "、".join(f"{w}→{s}" + (f"（{p}）" if p else "") for w, s, p in accepted))
    else:
        print("  没有找到需要纠正读音的词和数字")
    if rejected:
        warnings.append(f"这些读音建议没有采用，需要的话自己写进 pronunciation：{'；'.join(rejected)}")
    return {w: s for w, s, _ in accepted}


def check_style(obj) -> tuple[str, str]:
    """返回 (画风名称, 写进 imageStyle 的完整画风)；末尾统一加上构图要求，保证给标题、字幕留出位置，图里不出字。"""
    if not isinstance(obj, dict):
        raise PlanError("输出的不是 JSON 对象")
    name = re.sub(r"\s+", "", str(obj.get("name") or "")).strip("「」『』“”\"'《》")[:12]
    style = " ".join(str(obj.get("style") or "").split()).rstrip("，。,.；; ")
    if len(style) < 15:
        raise PlanError("style 没有写，或者太短")
    return name, f"{style[:200]}，{be.STYLE_SUFFIX}"


def design_style(cfg, heading: str, text: str, warnings: list[str], on_fail: str) -> str | None:
    """让大模型按文案的题材、时代和基调推荐一个画风，返回写进 imageStyle 的完整画风；没推荐出来时返回 None，
    并把 on_fail（接下来怎么办）写进提醒。"""
    print(f"正在用 {env('LLM_MODEL')} 按内容推荐画风…")
    try:
        name, style = ask_json(cfg, STYLE_PROMPT, f"视频标题：{heading}\n\n文案：\n{text[:12000]}", check_style)
    except PlanError as err:
        warnings.append(f"没能让模型推荐画风（{err}），{on_fail}")
        return None
    print(f"  画风：{name or '（没有名称）'}——{style.removesuffix('，' + be.STYLE_SUFFIX)}")
    return style


def check_cast(obj) -> dict[str, str]:
    items = obj.get("cast") if isinstance(obj, dict) else obj
    if not isinstance(items, list):
        raise PlanError("没有 cast 数组")
    cast: dict[str, str] = {}
    stems: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = re.sub(r"\s+", "", str(item.get("name") or "")).strip("「」『』“”\"'《》")
        look = " ".join(str(item.get("look") or "").split())
        stem = be.cast_filename(name)
        if not name or not look or len(name) > 12 or stem in stems:
            continue
        stems.add(stem)
        cast[name] = look[:160]
    return dict(list(cast.items())[:MAX_CAST])


def design_cast(cfg, heading: str, text: str, warnings: list[str]) -> dict[str, str]:
    """让大模型列出反复出现的人物并固定外貌，返回写进 cast 的 {角色名: 外貌设定}。"""
    print(f"正在用 {env('LLM_MODEL')} 设计角色表（反复出现的人物和他们固定的外貌）…")
    try:
        cast = ask_json(cfg, CAST_PROMPT, f"视频标题：{heading}\n\n文案：\n{text[:12000]}", check_cast)
    except PlanError as err:
        warnings.append(f"没能让模型设计角色表（{err}），cast 是空的，同一人物在不同画面里可能长得不一样")
        return {}
    print(f"  角色表：{'、'.join(cast)}" if cast else "  文案里没有需要固定形象的人物")
    return cast


def consistency_hint(episode: str, scenes: list[dict]) -> str | None:
    """挑出场最多的角色，建议先只出几张有他的画面，看看人物是否前后一致。"""
    counts = Counter(n for sc in scenes if not sc.get("reuse") for n in sc.get("cast", []))
    if not counts:
        return None
    name = counts.most_common(1)[0][0]
    ids = [sc["id"] for sc in scenes if not sc.get("reuse") and name in sc.get("cast", [])][:3]
    return (f"想先看看人物是否前后一致，可以只出 {name} 出场的几张："
            f"npm run images -- {episode} --only {','.join(ids)}")


def restyle_storyboard(episode: str) -> bool:
    """给已有的分镜按内容重新推荐画风，只改 imageStyle，旧文件备份为 storyboard.bak.json。返回画风有没有变。"""
    cfg = require_llm()
    ep_dir = be.EPISODES_DIR / episode
    sb_path = ep_dir / "storyboard.json"
    sb = be.load_storyboard(sb_path)
    be.validate(sb)
    heading = f"{sb.get('title', '')}{'——' + sb['subtitle'] if sb.get('subtitle') else ''}"
    full_text = "\n".join(t for sc in sb["scenes"] for t in sc.get("lines", []))
    warnings: list[str] = []
    style = design_style(cfg, heading, full_text, warnings, on_fail="画风没有改动")
    changed = bool(style) and style != sb.get("imageStyle")
    if changed:
        sb["imageStyle"] = style
        shutil.copyfile(sb_path, ep_dir / "storyboard.bak.json")
        be.write_json(sb_path, sb)
        print("已更新画风，旧分镜备份为 storyboard.bak.json")
    elif style:
        print("和现在的画风一样，分镜没有改动")
    for w in warnings:
        print(f"注意：{w}")
    return changed


def create_storyboard(episode: str, md_path: Path, voice: str, rate: str, aspect: str,
                      image_count: int | None = None) -> int:
    """标出容易读错的词和数字 → 推荐画风、定角色表 → 配音（用于统计时长）→ 大模型分组写提示词 → 写入 storyboard.json。
    返回原本就在 images 里的图片数。image_count 不为空时，整集正好分成这么多个画面（--images）。"""
    cfg = require_llm()
    ep_dir = be.EPISODES_DIR / episode
    sb_path = ep_dir / "storyboard.json"
    pieces = be.script_pieces(md_path)
    if image_count is not None:  # 先检查张数，免得调用了大模型才发现不行
        sizes = [0]
        for unit, texts in pieces:
            if unit["kind"] == "chapter":
                sizes.append(0)
            else:
                sizes[-1] += len(texts)
        be.check_image_count(image_count, [n for n in sizes if n])
    title, subtitle = be.titles_from_filename(md_path)
    heading = f"{title}{'——' + subtitle if subtitle else ''}"
    full_text = "\n".join(t for _, ts in pieces for t in ts)
    warnings: list[str] = []
    pron = find_pronunciation(cfg, heading, full_text, warnings)
    style = design_style(cfg, heading, full_text, warnings,
                         on_fail=f"imageStyle 先空着，出图前运行 npm run storyboard -- {episode} --style 再推荐一次，或者自己填写")
    cast = design_cast(cfg, heading, full_text, warnings)
    # 按替换读音后的文字合成，和之后 voice 用的缓存一致，不会重复合成
    spoken = {t: be.apply_pronunciation(t, pron)[0] for _, ts in pieces for t in ts}
    be.synth_all(list(spoken.values()), voice, rate)
    be.clip_infos(list(spoken.values()), voice, rate)

    # 按章节切段：每段是 (段落名, 章节单元或 None, [(句子, 时长)])
    sections: list[tuple[str, dict | None, list[tuple[str, float]]]] = []
    current: list[tuple[str, float]] = []
    name, chapter_unit = "开场", None
    for unit, texts in pieces:
        if unit["kind"] == "chapter":
            sections.append((name, chapter_unit, current))
            label = f"{unit['kicker']}：{unit['title']}" if unit["kicker"] else unit["title"]
            name, chapter_unit, current = label, {"unit": unit, "texts": texts}, []
        else:
            current += [(t, be.line_duration(spoken[t], voice, rate)) for t in texts]
    sections.append((name, chapter_unit, current))
    wants = iter(be.allocate_images(image_count, [[d for _, d in lines] for _, _, lines in sections if lines])
                 if image_count is not None else [])
    batches = [(name, chapter, chunk_section(lines, next(wants, None)) if lines else [])
               for name, chapter, lines in sections]

    ctx = f"视频标题：{heading}\n完整文案（只用来理解上下文）：\n{full_text[:8000]}"
    total_calls = sum(len(chunks) for _, _, chunks in batches)
    print(f"正在用 {env('LLM_MODEL')} 写分镜（共 {total_calls} 段，每段通常需要 10–60 秒）…")

    scenes: list[dict] = []
    known: list[tuple[str, str]] = []
    n_img = n_ch = call = 0
    for name, chapter, chunks in batches:
        if chapter:
            n_ch += 1
            scenes.append(be.chapter_scene(n_ch, chapter["unit"], chapter["texts"]))
        prev: dict | None = None  # 本段的上一个画面，follow 只在同一段里衔接
        for chunk, count in chunks:
            call += 1
            started = time.time()
            # 限定张数时不复用前面的图，每个画面都有自己的图
            groups = plan_chunk(cfg, ctx, name, chunk, known if count is None else [], warnings, count, cast, prev)
            for g in groups:
                n_img += 1
                sid = f"S{n_img:02d}"
                scene: dict = {"id": sid}
                if g["reuse"]:
                    scene["reuse"] = g["reuse"]
                scene["visual"] = g["visual"]
                if not g["reuse"]:
                    scene["prompt"] = g["prompt"]
                    if g["cast"]:
                        scene["cast"] = g["cast"]
                    if g["follow"] and prev:
                        scene["follow"] = prev["id"]
                if g["motion"]:
                    scene["motion"] = g["motion"]
                scene["lines"] = [t for t, _ in chunk[g["from"] - 1:g["to"]]]
                scenes.append(scene)
                prev = scene
                if not g["reuse"] and g["visual"]:
                    known.append((sid, g["visual"]))
            print(f"  [{call}/{total_calls}] {name}：{len(chunk)} 句 → {len(groups)} 个画面（{time.time() - started:.0f} 秒）")

    ep_dir.mkdir(parents=True, exist_ok=True)
    stale_images = be.count_images(ep_dir)
    if sb_path.exists():
        shutil.copyfile(sb_path, ep_dir / "storyboard.bak.json")
        print("旧分镜已备份为 storyboard.bak.json")
    be.write_json(sb_path, be.new_storyboard(md_path, voice, rate, aspect, scenes, pron, cast, style))
    images = [s for s in scenes if s.get("type") != "chapter"]
    reused = sum(1 for s in images if s.get("reuse"))
    print(f"已写好分镜：{be.rel(sb_path)}（{len(images)} 个画面，其中 {reused} 个复用前面的图，需要出图 {len(images) - reused} 张）")
    if cast:
        followed = sum(1 for s in images if s.get("follow"))
        print(f"角色表写在 storyboard.json 的 cast 里（{len(cast)} 个角色）。出图时会先给每个角色画一张定妆图，"
              f"再作为参考图让人物前后一致；{followed} 个画面延续上一格的场景")
    if image_count is not None:
        seconds = sum(d for _, _, lines in sections for _, d in lines) / len(images)
        print(f"平均每张图停留约 {seconds:.0f} 秒"
              + ("。停留超过 30 秒时，镜头推拉会慢到几乎看不出来，可以适当增加 --images" if seconds > 30 else ""))
    if pron:
        print(f"上面改读的 {len(pron)} 处写在 storyboard.json 的 pronunciation 里，建议在预览里听一下；"
              f"读得不对就修改或删掉，再运行 npm run voice -- {episode}")
    for w in warnings:
        print(f"注意：{w}")
    return stale_images


def find_md(episode: str, script: str | None) -> Path:
    md_path = be.find_script(episode, script)
    if md_path is None or not md_path.exists():
        be.die(be.missing_script(episode))
    return md_path


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="用大模型把口播文案写成分镜")
    parser.add_argument("episode", help="集数编号，例如 002")
    parser.add_argument("--script", help="文案 .md 路径（默认自动找 texts/ 里以集数编号开头的 .md）")
    parser.add_argument("--force", action="store_true", help="已有 storyboard.json 时重新生成（旧文件会备份）")
    parser.add_argument("--voice", default="zh-CN-YunxiNeural", help="配音音色")
    parser.add_argument("--rate", default="+5%", help="语速，如 +5%% 或 -10%%")
    parser.add_argument("--aspect", default="9:16", choices=sorted(be.SIZES), help="画面比例")
    parser.add_argument("--images", type=int, help="整集只用这么多张图（每张图对应一段较长的台词），不加就每 5–10 秒一张")
    parser.add_argument("--style", action="store_true", help="给已有的分镜按内容重新推荐画风，只改 imageStyle（旧文件会备份）")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]+", args.episode):
        be.die("集数编号只能包含字母、数字和 -（例如 002）")

    load_env(be.ROOT)
    require_llm()
    sb_path = be.EPISODES_DIR / args.episode / "storyboard.json"
    build_args = argparse.Namespace(script=args.script, redraft=False, voice=args.voice, rate=args.rate, aspect=args.aspect)
    if args.style:
        if args.force:
            be.die("--style 只改现有分镜的画风，--force 按文案全部重写，不能一起用")
        if not sb_path.exists():
            be.die(f"还没有 {be.rel(sb_path)}：直接运行 npm run storyboard -- {args.episode} 即可，新写的分镜自带画风")
        if not shutil.which("ffmpeg"):
            be.die("没有找到 ffmpeg，请先安装（例如 winget install Gyan.FFmpeg）")
        if restyle_storyboard(args.episode):
            be.build(args.episode, build_args)
            print(f"已有的图片要重画才会用上新画风（会重新收费），全部重画：npm run images -- {args.episode} --force")
        return
    if sb_path.exists() and not args.force:
        be.die(f"{be.rel(sb_path)} 已经存在。要用 AI 重新生成请加 --force（旧文件会备份为 storyboard.bak.json）；"
               f"只想重新推荐画风、保留现有分镜，请用 --style")
    md_path = find_md(args.episode, args.script)
    if not shutil.which("ffmpeg"):
        be.die("没有找到 ffmpeg，请先安装（例如 winget install Gyan.FFmpeg）")

    stale_images = create_storyboard(args.episode, md_path, args.voice, args.rate, args.aspect, args.images)
    be.build(args.episode, build_args)
    print(f"建议先打开 public/episodes/{args.episode}/prompts.md 看一遍画面描述，不满意的地方可以直接改 storyboard.json 或让 AI 改。")
    hint = consistency_hint(args.episode, be.load_storyboard(sb_path)["scenes"])
    if hint:
        print(hint)
    if stale_images:
        be.warn_stale_images(args.episode, stale_images)


if __name__ == "__main__":
    main()
