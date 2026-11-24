# /// script
# requires-python = ">=3.10"
# dependencies = ["edge-tts>=7.2"]
# ///
"""口播文案 → 配音 + 字幕时间轴 + 分镜时间线（供 Remotion 渲染）。

在项目根目录运行（001 是集数编号）：
    npm run voice -- 001
等价于：
    uv run scripts/build_episode.py 001

- 第一次运行且 public/episodes/001/storyboard.json 不存在时，会读取根目录下以 "001" 开头的
  .md 文案：先逐句配音，再按配音时长自动分组，生成一份分镜草稿。
- 之后以 storyboard.json 为准：改台词、改分镜分组、写出图提示词都改这个文件，再重新运行本命令。
- 配音按句缓存在 .cache/tts，只有改动过的句子才会重新合成。
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import wave
from array import array
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parent.parent
EPISODES_DIR = ROOT / "public" / "episodes"
CACHE_DIR = ROOT / ".cache" / "tts"
NARRATION_CACHE = ROOT / ".cache" / "narration"  # 每集的 narration.wav 是按哪些台词和停顿拼出来的
REGISTRY = ROOT / "src" / "episodes.json"

SAMPLE_RATE = 24000
CLIP_CACHE_VERSION = 1  # 改了 trim_silence 的裁剪规则就加一，让缓存里每句配音的时长重新计算
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
MOTIONS = ("zoomIn", "panRight", "zoomOut", "panLeft", "panUp", "zoomIn", "panDown")
SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "3:4": (1080, 1440)}
ASPECT_HINT = {"9:16": "竖版9:16构图", "16:9": "横版16:9构图", "1:1": "方形1:1构图", "3:4": "竖版3:4构图"}
DEFAULT_PAUSES = {"line": 0.35, "scene": 0.5, "chapterBefore": 0.6, "chapterAfter": 0.6, "end": 1.5}
TARGET_LUFS = -16.0  # loudnorm 的目标；动态模式下单声道配音实际约 -18，Remotion 输出双声道后成片约 -15 LUFS
TRUE_PEAK = -3.0  # 给 AAC 编码的峰值过冲留余量，避免成片削波
# 追加在大模型推荐的画风后面的构图要求：上方留给标题、下方留给字幕，图里不要有字
STYLE_SUFFIX = "主体清晰、位于画面中部，画面上方和下方留出较简洁的空间，画面中不要出现任何文字、字母、题款、印章或水印"
# 负面提示词：只有支持它的生图接口（如千问生图）会用到，也可以粘贴到网页工具的「不希望出现」一栏
DEFAULT_NEGATIVE = "文字，字母，水印，印章，签名，标志，边框，低画质，模糊，畸形的手"
CAST_DIR = "cast"  # 角色定妆图放在 images/cast/ 里，文件名是角色名

CAPTION_MAX = 15  # 每条字幕最多显示的字数（竖屏一行）
SCENE_TARGET = 7.5  # 自动分镜：每个画面的目标时长（秒）
SCENE_MAX = 12.0  # 自动分镜：单个画面最长时长（秒）

SECTION_WORDS = {"开场": "开场", "引言": "引言", "前言": "前言", "结尾": "结语", "结语": "结语", "总结": "总结", "尾声": "尾声"}
HEADING_RE = re.compile(r"^(第[一二三四五六七八九十百零〇两\d]+(?:阶段|部分|章|节|集|回|篇|幕))\s*[：:、.．\s]\s*(.+)$")
# 小标题开头的序号（一、 / （一） / 1、），只显示在章节卡上，不朗读
ORDINAL_RE = re.compile(r"^(?:[（(]\s*[一二三四五六七八九十百零〇两\d]+\s*[)）]|[一二三四五六七八九十百零〇两]+\s*[、.．]|\d+\s*[、.．)）])\s*")
FENCE_RE = re.compile(r"^(?:```|~~~)")
HR_RE = re.compile(r"^([-*_])(?:\s*\1){2,}$")  # 分隔线 --- *** ___
SETEXT_RE = re.compile(r"^=+$")
TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?$")
LINK_DEF_RE = re.compile(r"^\[[^\]]+\]:\s*\S")  # [id]: 网址、[^1]: 脚注
HASHTAG_LINE_RE = re.compile(r"^#[^\s#]+#?(?:\s*#[^\s#]+#?)+$|^#[^#]+#$")  # 整行都是话题标签
YAML_LINE_RE = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_-]*:(?:\s|$)|\s+\S|-\s)")
URL_RE = re.compile(r"https?://[^\s\u3000-\u303f\uff00-\uffef\u4e00-\u9fff]+")
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D\u20E3]")
SENTENCE_RE = re.compile(r"[^。！？!?]+[。！？!?]*[”’」』）)]*")
BREAK_CHARS = set("，。！？；：、,.!?;:…—")
CLOSERS = set("”’」』）)》")
PUNCT = BREAK_CHARS | CLOSERS | set("“‘「『（(《·\"' 　")
TRAILING = "，。、；：,.;:—"


# ---------------------------------------------------------------- 文案解析


def clean_md_line(line: str) -> tuple[str, int]:
    """去掉一行文案里的 Markdown / HTML 格式符号、网址和 Emoji，返回 (文字, 标题级别)，不是标题时级别为 0。"""
    s = line.strip().lstrip("\ufeff")
    level = 0
    m = re.match(r"^(#{1,6})\s+", s)
    if m:
        level = len(m.group(1))
        s = re.sub(r"\s+#+\s*$", "", s[m.end():])
    else:
        s = re.sub(r"^(?:>\s*)+", "", s)
        s = re.sub(r"^(?:[-*+]|\d+[.)、])\s+", "", s)
        s = re.sub(r"^\[[ xX]\]\s+", "", s)
    if s.startswith("|") and s.endswith("|"):  # 表格行：各单元格用逗号连起来
        s = "，".join(c.strip() for c in s.strip("|").split("|") if c.strip())
    s = re.sub(r"\\([!-/:-@\[-`{-~])", r"\1", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)  # 图片
    s = re.sub(r"\[\^[^\]]*\]", "", s)  # 脚注
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)|\[([^\]]*)\]\[[^\]]*\]", lambda mm: mm.group(1) or mm.group(2) or "", s)  # 链接只留文字
    s = re.sub(r"</?[A-Za-z][^>]*>", "", s)  # HTML 标签、<网址>
    s = URL_RE.sub("", s)
    s = re.sub(r"[（(]\s*[)）]|【\s*】|\[\s*\]", "", s)  # 去掉网址后留下的空括号
    while True:  # 加粗、斜体、删除线、高亮：去掉符号，保留文字
        t = re.sub(r"(?<!\d)(\*{1,3}|~~|==)(?=\S)(.+?)(?<=\S)\1", r"\2", s)
        t = re.sub(r"(?<![A-Za-z0-9])(_{1,3})(?=\S)(.+?)(?<=\S)\1(?![A-Za-z0-9])", r"\2", t)
        if t == s:
            break
        s = t
    s = re.sub(r"(?<!\d)\*|\*(?!\d)", "", s)  # 落单的星号（3*4 这样的算式不动）
    s = re.sub(r"_{2,}|~~|==|`|#", "", s)
    s = EMOJI_RE.sub("", s)
    return re.sub(r"[ \t]{2,}", " ", s).strip(), level


def front_matter_end(lines: list[str]) -> int:
    """文件开头 --- 之间的 YAML 头信息（title: xxx 这类）不是文案，返回正文开始的行号。"""
    if not lines or lines[0].strip() != "---":
        return 0
    for i in range(1, min(len(lines), 60)):
        s = lines[i]
        if s.strip() in ("---", "..."):
            return i + 1 if i > 1 else 0
        if s.strip() and not YAML_LINE_RE.match(s):
            return 0
    return 0


def is_layout_line(s: str) -> bool:
    """只用来排版、没有台词的行：代码块围栏、分隔线、表格分隔行、链接定义、整行话题标签。"""
    return bool(FENCE_RE.match(s) or HR_RE.match(s) or SETEXT_RE.match(s) or LINK_DEF_RE.match(s)
                or HASHTAG_LINE_RE.match(s) or ("|" in s and TABLE_SEP_RE.match(s)))


def speakable(text: str) -> bool:
    # 只剩标点、符号的行没有可读的内容，还会让配音报错
    return any(ch.isalnum() for ch in text)


def parse_script(md_path: Path) -> list[dict]:
    """返回按顺序排列的单元：{"kind": "line"|"chapter", "text", "kicker", "title"}，text 是要朗读的文字。"""
    raw = md_path.read_text(encoding="utf-8-sig")
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S)  # HTML 注释
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    lines = raw.splitlines()
    units: list[dict] = []
    for raw_line in lines[front_matter_end(lines):]:
        s = raw_line.strip()
        if not s or is_layout_line(s):
            continue
        text, level = clean_md_line(s)
        if not speakable(text):
            continue
        bare = ORDINAL_RE.sub("", text)
        m = HEADING_RE.match(text)
        section = SECTION_WORDS.get(bare.rstrip("：:。.！!"))
        if m:
            units.append({"kind": "chapter", "text": text, "kicker": m.group(1), "title": m.group(2).strip()})
        elif section:
            units.append({"kind": "chapter", "text": "", "kicker": "", "title": section})
        elif level:
            if level == 1 and not units:  # 文档最开头的一级标题视为整篇标题，不朗读
                continue
            units.append({"kind": "chapter", "text": bare if speakable(bare) else "", "kicker": "", "title": text})
        else:
            units.append({"kind": "line", "text": text})
    return units


def titles_from_filename(md_path: Path) -> tuple[str, str]:
    name = re.sub(r"^\d+[.\s_-]*", "", md_path.stem)
    title, _, subtitle = name.partition("——")
    return title.strip() or name, subtitle.strip()


def find_script(episode: str, explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.is_absolute() else (Path.cwd() / p)
    found = sorted(p for p in ROOT.glob(f"{episode}*.md") if p.is_file())
    return found[0] if found else None


# ---------------------------------------------------------------- 配音（edge-tts，按句缓存）


def apply_pronunciation(text: str, pron: dict[str, str]) -> tuple[str, list[int]]:
    """按发音替换表生成朗读文本，同时返回「显示文字下标 → 朗读文字下标」的映射。"""
    if not pron:
        return text, list(range(len(text)))
    keys = sorted((k for k in pron if k), key=len, reverse=True)
    out: list[str] = []
    mapping: list[int] = []
    cur = 0
    i = 0
    while i < len(text):
        for k in keys:
            if text.startswith(k, i):
                v = pron[k]
                for j in range(len(k)):
                    mapping.append(cur + min(max(len(v) - 1, 0), j * len(v) // len(k)))
                out.append(v)
                cur += len(v)
                i += len(k)
                break
        else:
            mapping.append(cur)
            out.append(text[i])
            cur += 1
            i += 1
    return "".join(out), mapping


def cache_paths(tts_text: str, voice: str, rate: str) -> tuple[Path, Path]:
    key = hashlib.sha1(json.dumps([voice, rate, tts_text], ensure_ascii=False).encode("utf-8")).hexdigest()[:20]
    return CACHE_DIR / f"{key}.mp3", CACHE_DIR / f"{key}.json"


async def synth_one(tts_text: str, voice: str, rate: str, sem: asyncio.Semaphore, progress: list[int]) -> None:
    mp3, meta = cache_paths(tts_text, voice, rate)
    if mp3.exists() and meta.exists():
        return
    async with sem:
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                comm = edge_tts.Communicate(tts_text, voice, rate=rate, boundary="WordBoundary")
                audio = bytearray()
                words = []
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        audio.extend(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        s = chunk["offset"] / 1e7
                        words.append([round(s, 4), round(s + chunk["duration"] / 1e7, 4), chunk["text"]])
                if not audio:
                    raise RuntimeError("没有收到音频数据")
                mp3.write_bytes(bytes(audio))
                meta.write_text(
                    json.dumps({"text": tts_text, "voice": voice, "rate": rate, "words": words}, ensure_ascii=False),
                    encoding="utf-8",
                )
                progress[0] += 1
                if progress[0] % 10 == 0 or progress[0] == progress[1]:
                    print(f"  已合成 {progress[0]}/{progress[1]}")
                return
            except Exception as err:  # 网络抖动时重试
                last_err = err
                await asyncio.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"配音失败：「{tts_text[:24]}」：{last_err}")


def synth_all(tts_texts: list[str], voice: str, rate: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    uniq = list(dict.fromkeys(tts_texts))
    todo = [t for t in uniq if not all(p.exists() for p in cache_paths(t, voice, rate))]
    print(f"配音（{voice}，语速 {rate}）：共 {len(uniq)} 句，需新合成 {len(todo)} 句，其余用缓存")
    if not todo:
        return

    async def run() -> None:
        sem = asyncio.Semaphore(4)
        progress = [0, len(todo)]
        await asyncio.gather(*(synth_one(t, voice, rate, sem, progress) for t in todo))

    asyncio.run(run())


def trim_silence(pcm: bytes, words: list) -> tuple[bytes, list]:
    """裁掉每句首尾的静音（edge-tts 每句自带约 0.1 秒前导、0.5 秒尾部静音），句间停顿统一由 pauses 控制。"""
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder == "big":
        samples.byteswap()
    n = len(samples)
    win = SAMPLE_RATE // 100
    threshold = 300  # 约 -40 dBFS

    def loud(i: int) -> bool:
        return max(map(abs, samples[i:i + win]), default=0) > threshold

    a = 0
    while a < n and not loud(a):
        a += win
    b = n
    while b > a and not loud(max(b - win, 0)):
        b -= win
    if a >= b:
        return pcm, words
    a = max(0, a - int(0.04 * SAMPLE_RATE))
    b = min(n, b + int(0.12 * SAMPLE_RATE))
    lead = a / SAMPLE_RATE
    shifted = [[max(0.0, s - lead), max(0.0, e - lead), w] for s, e, w in words]
    return pcm[a * 2:b * 2], shifted


def load_tts(tts_text: str, voice: str, rate: str) -> tuple[bytes, list]:
    mp3, meta = cache_paths(tts_text, voice, rate)
    pcm = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(mp3), "-f", "s16le", "-acodec", "pcm_s16le",
         "-ac", "1", "-ar", str(SAMPLE_RATE), "-"],
        capture_output=True, check=True,
    ).stdout
    words = json.loads(meta.read_text(encoding="utf-8"))["words"]
    return trim_silence(pcm, words)


def clip_info(tts_text: str, voice: str, rate: str) -> tuple[int, list]:
    """一句配音裁掉首尾静音后的采样数和逐词时间。第一次要解码 mp3，结果记进配音缓存的 json，以后直接读。"""
    _, meta = cache_paths(tts_text, voice, rate)
    data = json.loads(meta.read_text(encoding="utf-8"))
    trimmed = data.get("trimmed")
    if not trimmed or trimmed.get("version") != CLIP_CACHE_VERSION:
        pcm, words = load_tts(tts_text, voice, rate)
        trimmed = data["trimmed"] = {"version": CLIP_CACHE_VERSION, "samples": len(pcm) // 2, "words": words}
        tmp = meta.with_name(f"{meta.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(meta)
    return trimmed["samples"], trimmed["words"]


def clip_infos(tts_texts: list[str], voice: str, rate: str) -> dict[str, tuple[int, list]]:
    """批量取 clip_info，还没解码过的几句并行解码。"""
    uniq = list(dict.fromkeys(tts_texts))
    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(zip(uniq, pool.map(lambda t: clip_info(t, voice, rate), uniq)))


def write_narration(path: Path, plan: list, voice: str, rate: str) -> None:
    """按拼接步骤写出整条配音：数字是一段静音的采样数，文字是一句配音（裁掉首尾静音后）。"""
    texts = list(dict.fromkeys(step for step in plan if isinstance(step, str)))
    with ThreadPoolExecutor(max_workers=8) as pool:
        audio = dict(zip(texts, pool.map(lambda t: load_tts(t, voice, rate)[0], texts)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        for step in plan:
            w.writeframes(b"\x00\x00" * step if isinstance(step, int) else audio[step])


def narration_current(path: Path, stamp: Path, key: str) -> bool:
    """narration.wav 是不是按同样的台词和停顿拼出来的，而且之后没被改动过。"""
    try:
        data = json.loads(stamp.read_text(encoding="utf-8"))
        st = path.stat()
    except (OSError, ValueError):
        return False
    return data.get("key") == key and data.get("size") == st.st_size and data.get("mtime") == st.st_mtime_ns


def measure_loudness(path: Path) -> dict | None:
    probe = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
         f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", probe.stderr)
    try:
        stats = json.loads(m.group(0)) if m and probe.returncode == 0 else None
        return stats if stats and math.isfinite(float(stats["input_i"])) else None
    except (ValueError, KeyError):
        return None


def normalize_loudness(path: Path) -> tuple[float, float] | None:
    """两遍 loudnorm：先测量整条配音的响度，再统一到 TARGET_LUFS 附近。返回 (原始响度, 处理后响度)。"""
    stats = measure_loudness(path)
    if stats is None:
        print("注意：配音响度测量失败，本次跳过响度统一")
        return None
    tmp = path.with_name(path.stem + ".norm.wav")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(path), "-af",
         f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=11:measured_I={stats['input_i']}"
         f":measured_TP={stats['input_tp']}:measured_LRA={stats['input_lra']}"
         f":measured_thresh={stats['input_thresh']}:offset={stats['target_offset']}:linear=true",
         "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(tmp)],
        check=True,
    )
    tmp.replace(path)
    after = measure_loudness(path)
    return float(stats["input_i"]), float(after["input_i"]) if after else TARGET_LUFS


# ---------------------------------------------------------------- 字幕切分


def visible_len(s: str) -> float:
    return sum(0 if (ch in PUNCT or ch.isspace()) else (0.5 if ord(ch) < 128 else 1) for ch in s)


def char_times(display: str, tts_text: str, mapping: list[int], words: list) -> tuple[list, list]:
    """把逐词时间戳落到显示文字的每个字上；返回 (每字时间, 每字所属词序号)。"""
    t_times: list = [None] * len(tts_text)
    t_word: list = [None] * len(tts_text)
    pos = 0
    for wi, (s, e, w) in enumerate(words):
        w = w.strip()
        if not w:
            continue
        idx = tts_text.find(w, pos, pos + len(w) + 8)
        if idx < 0:
            continue
        n = len(w)
        for k in range(n):
            t_times[idx + k] = (s + (e - s) * k / n, s + (e - s) * (k + 1) / n)
            t_word[idx + k] = wi
        pos = idx + n
    d_times = [t_times[m] if m < len(t_times) else None for m in mapping]
    d_word = [t_word[m] if m < len(t_word) else None for m in mapping]
    return d_times, d_word


def clause_spans(text: str) -> list[tuple[int, int]]:
    spans, start, i, n = [], 0, 0, len(text)
    while i < n:
        if text[i] in BREAK_CHARS:
            j = i
            while j < n and (text[j] in BREAK_CHARS or text[j] in CLOSERS):
                j += 1
            spans.append((start, j))
            start = i = j
        else:
            i += 1
    if start < n:
        spans.append((start, n))
    return [(a, b) for a, b in spans if visible_len(text[a:b]) > 0]


def merge_short(text: str, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in spans:
        if out:
            pa, pb = out[-1]
            prev_len, cur_len = visible_len(text[pa:pb]), visible_len(text[a:b])
            ends_sentence = text[pa:pb].rstrip()[-1:] in "。！？!?"
            if (prev_len <= 4 or cur_len <= 3) and prev_len + cur_len <= CAPTION_MAX and not ends_sentence:
                out[-1] = (pa, b)
                continue
        out.append((a, b))
    return out


def split_long(text: str, spans: list[tuple[int, int]], word_starts: set[int]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for a, b in spans:
        total = visible_len(text[a:b])
        if total <= CAPTION_MAX:
            result.append((a, b))
            continue
        target = total / math.ceil(total / CAPTION_MAX)
        start = a
        while visible_len(text[start:b]) > CAPTION_MAX:
            best = None
            for c in sorted(x for x in word_starts if start < x < b):
                length = visible_len(text[start:c])
                if length > CAPTION_MAX:
                    break
                if best is None or abs(length - target) < abs(visible_len(text[start:best]) - target):
                    best = c
            if best is None:  # 没有词边界可用时按字数硬切
                best = start + 1
                while best < b and visible_len(text[start:best]) < target:
                    best += 1
            result.append((start, best))
            start = best
        result.append((start, b))
    return result


def line_captions(display: str, tts_text: str, mapping: list[int], words: list, t0: float, t1: float) -> list[dict]:
    d_times, d_word = char_times(display, tts_text, mapping, words)
    word_starts = {i for i in range(1, len(display)) if d_word[i] is not None and d_word[i] != d_word[i - 1]}
    spans = split_long(display, merge_short(display, clause_spans(display)), word_starts)
    caps: list[dict] = []
    for a, b in spans:
        ts = [d_times[i] for i in range(a, b) if d_times[i] is not None]
        text = display[a:b].strip().rstrip(TRAILING).strip()
        if not text:
            continue
        caps.append({"text": text, "start": t0 + ts[0][0] if ts else None, "end": t0 + ts[-1][1] if ts else None})
    # 补齐没有对上时间戳的片段：按字数在相邻片段之间插值
    for i, c in enumerate(caps):
        if c["start"] is None:
            prev_end = caps[i - 1]["end"] if i > 0 and caps[i - 1]["end"] is not None else t0
            nxt = next((x["start"] for x in caps[i + 1:] if x["start"] is not None), t1)
            c["start"], c["end"] = prev_end, max(prev_end + 0.3, nxt)
    for i in range(len(caps) - 1):  # 同一句内的字幕首尾相接，避免闪烁
        caps[i]["end"] = caps[i + 1]["start"]
    if caps:
        caps[-1]["end"] = min(t1, caps[-1]["end"] + 0.25)
    return caps


def finalize_captions(caps: list[dict]) -> list[dict]:
    caps.sort(key=lambda c: c["start"])
    for i, c in enumerate(caps):
        if i + 1 < len(caps):
            gap = caps[i + 1]["start"] - c["end"]
            # 句间停顿很短时让上一条字幕停留到下一条出现，避免字幕闪断
            c["end"] = caps[i + 1]["start"] if gap < 0.6 else min(c["end"], caps[i + 1]["start"])
        c["end"] = max(c["end"], c["start"] + 0.2)
        c["start"], c["end"] = round(c["start"], 3), round(c["end"], 3)
    return caps


# ---------------------------------------------------------------- 分镜草稿


def script_pieces(md_path: Path) -> list[tuple[dict, list[str]]]:
    """文案单元 + 每个单元要朗读的句子（过长的段落按句拆开，方便分镜）。"""
    units = parse_script(md_path)
    if not any(u["kind"] == "line" for u in units):
        die(f"{md_path.name} 里没有读到正文")
    pieces: list[tuple[dict, list[str]]] = []
    for u in units:
        if u["kind"] == "line" and len(u["text"]) > 45:
            parts = [p.strip() for p in SENTENCE_RE.findall(u["text"]) if p.strip()]
            pieces.append((u, parts or [u["text"]]))
        else:
            pieces.append((u, [u["text"]] if u["text"] else []))
    return pieces


def line_duration(text: str, voice: str, rate: str) -> float:
    return clip_info(text, voice, rate)[0] / SAMPLE_RATE


def chapter_scene(n: int, unit: dict, texts: list[str]) -> dict:
    return {"id": f"C{n}", "type": "chapter", "kicker": unit["kicker"], "title": unit["title"], "lines": texts}


def new_storyboard(md_path: Path, voice: str, rate: str, aspect: str, scenes: list[dict],
                   pronunciation: dict[str, str] | None = None, cast: dict[str, str] | None = None,
                   style: str | None = None) -> dict:
    title, subtitle = titles_from_filename(md_path)
    return {
        "title": title,
        "subtitle": subtitle,
        "aspect": aspect,
        "fps": 30,
        "voice": voice,
        "rate": rate,
        "pauses": dict(DEFAULT_PAUSES),
        "pronunciation": pronunciation or {},
        "bgm": None,
        "imageStyle": style or "",
        "negativePrompt": DEFAULT_NEGATIVE,
        "cast": cast or {},
        "scenes": scenes,
    }


def time_groups(durations: list[float]) -> list[tuple[int, int]]:
    """按配音时长把相邻的句子分组：凑够 SCENE_TARGET 秒就换画面，尽量不超过 SCENE_MAX 秒。
    返回 [(起, 止)]，句子编号从 1 开始、包含两端。"""
    groups, start, dur = [], 1, 0.0
    for i, d in enumerate(durations, 1):
        if i > start and (dur >= SCENE_TARGET or dur + d > SCENE_MAX):
            groups.append((start, i - 1))
            start, dur = i, 0.0
        dur += d + DEFAULT_PAUSES["line"]
    groups.append((start, len(durations)))
    return groups


def even_groups(durations: list[float], count: int) -> list[tuple[int, int]]:
    """把相邻的句子按顺序正好分成 count 组，各组时长尽量接近。返回格式同 time_groups。"""
    ends, total = [], 0.0
    for d in durations:
        total += d
        ends.append(total)
    edges = [0]
    for j in range(1, count):
        # 每组至少一句，还要给后面的每组各留一句
        edges.append(min(range(edges[-1] + 1, len(durations) - count + j + 1),
                         key=lambda i: abs(ends[i - 1] - total * j / count)))
    edges.append(len(durations))
    return [(edges[i] + 1, edges[i + 1]) for i in range(count)]


def check_image_count(total: int, sizes: list[int]) -> None:
    """检查 --images 是否可行。sizes 是按章节切段后各段（开场、各章节）的句子数，不含没有句子的段。"""
    if total < len(sizes):
        die(f"这篇文案按章节分成 {len(sizes)} 段，每段至少要 1 张图，--images 不能小于 {len(sizes)}")
    if total > sum(sizes):
        die(f"文案一共只有 {sum(sizes)} 句，每张图至少对应一句，--images 不能大于 {sum(sizes)}")


def allocate_images(total: int, sections: list[list[float]]) -> list[int]:
    """整集只用 total 张图时，每段分几张。sections 是各段每句的配音时长。
    每段至少 1 张、最多每句 1 张；多出来的优先给「每张图停留最久」的段，让整集每张图的停留时长尽量接近。"""
    check_image_count(total, [len(s) for s in sections])
    counts = [1] * len(sections)
    seconds = [sum(s) for s in sections]
    for _ in range(total - len(sections)):
        i = max((i for i, s in enumerate(sections) if counts[i] < len(s)), key=lambda i: seconds[i] / counts[i])
        counts[i] += 1
    return counts


def make_draft(episode: str, md_path: Path, voice: str, rate: str, aspect: str, image_count: int | None = None) -> dict:
    pieces = script_pieces(md_path)
    texts = [t for _, ts in pieces for t in ts]
    synth_all(texts, voice, rate)
    clip_infos(texts, voice, rate)

    # 按章节切段：每段是 (章节单元和它要读的句子，开场为 None；[(句子, 时长)])
    sections: list[tuple[tuple[dict, list[str]] | None, list[tuple[str, float]]]] = [(None, [])]
    for u, texts in pieces:
        if u["kind"] == "chapter":
            sections.append(((u, texts), []))
        else:
            sections[-1][1].extend((t, line_duration(t, voice, rate)) for t in texts)
    counts = iter(allocate_images(image_count, [[d for _, d in lines] for _, lines in sections if lines])
                  if image_count else [])

    scenes: list[dict] = []
    n_img = n_ch = 0
    for chapter, lines in sections:
        if chapter:
            n_ch += 1
            scenes.append(chapter_scene(n_ch, *chapter))
        if not lines:
            continue
        durations = [d for _, d in lines]
        for a, b in even_groups(durations, next(counts)) if image_count else time_groups(durations):
            n_img += 1
            scenes.append({"id": f"S{n_img:02d}", "visual": "", "prompt": "", "lines": [t for t, _ in lines[a - 1:b]]})
    return new_storyboard(md_path, voice, rate, aspect, scenes)


# ---------------------------------------------------------------- 构建


def die(msg: str) -> None:
    sys.stdout.flush()
    print(f"错误：{msg}", file=sys.stderr)
    sys.exit(1)


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_storyboard(sb_path: Path) -> dict:
    try:
        return json.loads(sb_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as err:
        die(
            f"{rel(sb_path)} 格式有误（第 {err.lineno} 行第 {err.colno} 列）：{err.msg}\n"
            "  常见原因：漏了或多了逗号、引号没配对、用了中文引号包裹字段名。也可以让 AI 帮你修好这个文件。"
        )


def validate(sb: dict) -> None:
    scenes = sb.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        die("storyboard.json 里没有 scenes")
    seen: set[str] = set()
    for sc in scenes:
        sid = sc.get("id")
        if not sid or sid in seen:
            die(f"分镜编号缺失或重复：{sid!r}")
        seen.add(sid)
        if not isinstance(sc.get("lines", []), list):
            die(f"{sid} 的 lines 必须是数组")
    for sc in scenes:
        if sc.get("reuse") and sc["reuse"] not in seen:
            die(f"{sc['id']} 复用的分镜 {sc['reuse']} 不存在")
    if sb.get("aspect", "9:16") not in SIZES:
        die(f"aspect 只支持 {', '.join(SIZES)}")
    cast = sb.get("cast") or {}
    if not isinstance(cast, dict) or not all(isinstance(k, str) and k.strip() and isinstance(v, str)
                                             for k, v in cast.items()):
        die('cast（角色表）的格式应该是 {"角色名": "外貌设定", ...}')
    stems: dict[str, str] = {}
    for name in cast:
        other = stems.setdefault(cast_filename(name), name)
        if other != name:
            die(f"角色名「{name}」和「{other}」去掉空格、符号后相同，定妆图会重名，请改掉一个")
    earlier: set[str] = set()
    for sc in scenes:
        names = sc.get("cast", [])
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            die(f'{sc["id"]} 的 cast 必须是角色名数组，例如 ["东汉少年皇帝"]')
        unknown = [n for n in names if n not in cast]
        if unknown:
            die(f"{sc['id']} 的 cast 里有角色表没有的角色：{'、'.join(unknown)}（角色表是 storyboard.json 开头的 cast）")
        if sc.get("follow") and sc["follow"] not in earlier:
            die(f"{sc['id']} 的 follow 要写它前面某个画面的编号（不能是章节卡），现在是 {sc['follow']!r}")
        if sc.get("type") != "chapter":
            earlier.add(sc["id"])


def check_drift(md_path: Path, sb: dict) -> None:
    def norm(s: str) -> str:
        return re.sub(r"\s+", "", s)

    md_text = norm("".join(u["text"] for u in parse_script(md_path)))
    sb_text = norm("".join(t for sc in sb["scenes"] for t in sc.get("lines", [])))
    if md_text == sb_text:
        return
    i = next((k for k, (x, y) in enumerate(zip(md_text, sb_text)) if x != y), min(len(md_text), len(sb_text)))
    print(f"注意：storyboard.json 的台词与 {md_path.name} 不一致（第 {i} 字附近）")
    print(f"  文案：…{md_text[max(0, i - 8):i + 16]}…")
    print(f"  分镜：…{sb_text[max(0, i - 8):i + 16]}…")
    print("  当前以 storyboard.json 为准；想按文案重新生成分镜请加 --redraft（会覆盖分组和提示词）")


def image_file(folder: Path, stem: str) -> Path | None:
    for ext in IMAGE_EXTS:
        for name in (stem + ext, stem + ext.upper()):
            if (folder / name).exists():
                return folder / name
    return None


def find_image(ep_dir: Path, episode: str, scene_id: str) -> str | None:
    f = image_file(ep_dir / "images", scene_id)
    return f"episodes/{episode}/images/{f.name}" if f else None


def cast_filename(name: str) -> str:
    """角色定妆图的文件名（不含扩展名）：去掉文件名里不能用的符号和空白。"""
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("._") or "角色"


def find_cast_image(folder: Path, name: str) -> Path | None:
    return image_file(folder, cast_filename(name))


def follow_source(by_id: dict[str, dict], sc: dict) -> str | None:
    """follow 指向的画面实际用的是哪张图：指向复用别的图的分镜时，就是被复用的那张。"""
    target = by_id.get(sc.get("follow") or "")
    return (target.get("reuse") or target["id"]) if target else None


def cast_sheet_prompt(name: str, look: str, style: str) -> str:
    figure = (f"人物定妆图：{name}，{look.strip().rstrip('，。,. ')}。单人全身像，正面站立，神态平静，"
              "完整展示发型、服饰和配饰，纯浅灰色背景，没有其他人物和场景")
    return "，".join(p for p in (figure, style.strip().rstrip("，。,. ")) if p)


def scene_prompt(text: str, looks: list[tuple[str, str]], style: str, aspect: str) -> str:
    """出图提示词：画面描述 + 需要用文字说明外貌的角色 + 统一画风 + 构图比例。"""
    def clean(s: str) -> str:
        return s.strip().rstrip("，。,. ")

    tail = [p for p in (clean(style), ASPECT_HINT.get(aspect, "")) if p]
    if not looks:
        return "，".join(p for p in [clean(text), *tail] if p)
    described = "；".join(f"{name}：{look.strip().rstrip('，。,.；; ')}" for name, look in looks)
    return f"{clean(text)}。{described}。" + "，".join(tail)


def count_images(ep_dir: Path) -> int:
    folder = ep_dir / "images"
    return sum(1 for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS) if folder.is_dir() else 0


def warn_stale_images(episode: str, n: int) -> None:
    print(f"注意：images 文件夹里原来就有 {n} 张图，重新生成的分镜编号可能和这些旧图对不上。"
          f"请在预览里逐个检查，对不上的图删掉后重画（npm run images -- {episode} --only 分镜编号）")


def header_size(path: Path) -> tuple[int, int] | None:
    """从文件头读图片宽高，支持 PNG、JPEG、WebP；读不出来返回 None。"""
    with open(path, "rb") as f:
        head = f.read(30)
        if head.startswith(b"\x89PNG\r\n\x1a\n") and head[12:16] == b"IHDR":
            return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP" and len(head) == 30:
            kind = head[12:16]
            if kind == b"VP8X":
                return int.from_bytes(head[24:27], "little") + 1, int.from_bytes(head[27:30], "little") + 1
            if kind == b"VP8 ":
                return int.from_bytes(head[26:28], "little") & 0x3FFF, int.from_bytes(head[28:30], "little") & 0x3FFF
            if kind == b"VP8L":
                bits = int.from_bytes(head[21:25], "little")
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            return None
        if not head.startswith(b"\xff\xd8"):
            return None
        f.seek(2)
        while True:  # 逐个跳过 JPEG 的段，直到 SOF 段（里面记着宽高）
            marker = f.read(2)
            if len(marker) < 2 or marker[0] != 0xFF:
                return None
            code = marker[1]
            if code in (0xD9, 0xDA):  # 到了图像结尾或压缩数据，还没见到 SOF
                return None
            if code == 0xFF or code == 0x01 or 0xD0 <= code <= 0xD8:  # 填充字节和没有长度的标记
                if code == 0xFF:
                    f.seek(-1, 1)
                continue
            length = int.from_bytes(f.read(2), "big")
            if 0xC0 <= code <= 0xCF and code not in (0xC4, 0xC8, 0xCC):
                sof = f.read(5)
                return (int.from_bytes(sof[3:5], "big"), int.from_bytes(sof[1:3], "big")) if len(sof) == 5 else None
            if length < 2:
                return None
            f.seek(length - 2, 1)


def probe_size(path: Path) -> tuple[int, int] | None:
    try:
        size = header_size(path)
        if size and min(size) > 0:
            return size
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        w, h = (int(x) for x in out.split(",")[:2])
        return w, h
    except Exception:
        return None


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def build(episode: str, args: argparse.Namespace, verbose: bool = True, fill_missing: bool = False) -> dict:
    """生成配音、字幕、时间线和出图提示词。fill_missing=True 时，没有图片的分镜暂用相邻画面的图片（一键生成导出时用）。"""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        die("没有找到 ffmpeg，请先安装（例如 scoop install ffmpeg）")
    ep_dir = EPISODES_DIR / episode
    sb_path = ep_dir / "storyboard.json"
    md_path = find_script(episode, args.script)

    stale_images = 0
    if args.redraft or not sb_path.exists():
        if md_path is None or not md_path.exists():
            die(f"没找到第 {episode} 集的文案：请把文案放在项目根目录，文件名以 {episode} 开头（如 {episode}.标题.md），或用 --script 指定")
        ep_dir.mkdir(parents=True, exist_ok=True)
        stale_images = count_images(ep_dir)
        if sb_path.exists():
            shutil.copyfile(sb_path, ep_dir / "storyboard.bak.json")
            print("旧分镜已备份为 storyboard.bak.json")
        draft = make_draft(episode, md_path, args.voice, args.rate, args.aspect, getattr(args, "images", None))
        write_json(sb_path, draft)
        print(f"已根据 {md_path.name} 生成分镜草稿：{rel(sb_path)}"
              "（画风 imageStyle 和每个分镜的 visual、prompt 待填写，可用 npm run storyboard 让 AI 来写）")

    sb = load_storyboard(sb_path)
    validate(sb)
    if md_path and md_path.exists():
        check_drift(md_path, sb)

    voice = sb.get("voice", "zh-CN-YunyangNeural")
    rate = sb.get("rate", "+0%")
    pauses = {**DEFAULT_PAUSES, **(sb.get("pauses") or {})}
    pron = sb.get("pronunciation") or {}
    aspect = sb.get("aspect", "9:16")
    width, height = SIZES[aspect]
    fps = int(sb.get("fps", 30))
    style = sb.get("imageStyle") or ""

    narr: dict[str, tuple[str, list[int]]] = {}
    for sc in sb["scenes"]:
        for t in sc.get("lines", []):
            narr[t] = apply_pronunciation(t, pron)
    synth_all([v[0] for v in narr.values()], voice, rate)
    clips = clip_infos([v[0] for v in narr.values()], voice, rate)

    # 先只排时间线：plan 记下配音怎么拼（数字是静音的采样数，文字是一句配音），真正拼接留到配音有改动时
    plan: list = []
    samples = 0

    def now() -> float:
        return samples / SAMPLE_RATE

    def silence(sec: float) -> None:
        nonlocal samples
        plan.append(int(round(sec * SAMPLE_RATE)))
        samples += plan[-1]

    scenes_out: list[dict] = []
    captions: list[dict] = []
    lines_out: list[dict] = []
    chapter_label = None
    n_image = 0
    for si, sc in enumerate(sb["scenes"]):
        is_chapter = sc.get("type") == "chapter"
        start = now()
        if si > 0:
            silence(pauses["chapterBefore"] if is_chapter else pauses["scene"])
        for li, text in enumerate(sc.get("lines", [])):
            if li > 0:
                silence(pauses["line"])
            tts_text, mapping = narr[text]
            length, words = clips[tts_text]
            t0 = now()
            plan.append(tts_text)
            samples += length
            t1 = now()
            lines_out.append({"scene": sc["id"], "text": text, "start": round(t0, 3), "end": round(t1, 3)})
            if not is_chapter:
                captions.extend(line_captions(text, tts_text, mapping, words, t0, t1))
        if is_chapter:
            silence(pauses["chapterAfter"] if sc.get("lines") else float(sc.get("hold", 1.8)))
            kicker, title = sc.get("kicker", ""), sc.get("title", "")
            chapter_label = f"{kicker} · {title}" if kicker else title
            scenes_out.append({"id": sc["id"], "type": "chapter", "start": round(start, 3),
                               "kicker": kicker, "title": title})
        else:
            if not sc.get("lines"):
                silence(float(sc.get("hold", 2.0)))
            source_id = sc.get("reuse") or sc["id"]
            scenes_out.append({
                "id": sc["id"], "type": "image", "start": round(start, 3),
                "image": find_image(ep_dir, episode, source_id),
                "source": source_id,
                "visual": sc.get("visual", ""),
                "motion": sc.get("motion") or MOTIONS[n_image % len(MOTIONS)],
                "chapter": chapter_label,
            })
            n_image += 1
    silence(pauses["end"])
    total = now()
    for i, s in enumerate(scenes_out):
        s["end"] = scenes_out[i + 1]["start"] if i + 1 < len(scenes_out) else round(total, 3)
    captions = finalize_captions(captions)

    filled: list[str] = []
    if fill_missing:
        image_out = [s for s in scenes_out if s["type"] == "image"]
        real = [s["image"] for s in image_out]
        for i, s in enumerate(image_out):
            if s["image"]:
                continue
            prev = next((real[j] for j in range(i - 1, -1, -1) if real[j]), None)
            nxt = next((real[j] for j in range(i + 1, len(real)) if real[j]), None)
            if prev or nxt:
                s["image"] = prev or nxt
                filled.append(s["id"])

    bgm = None
    if sb.get("bgm") and sb["bgm"].get("file"):
        f = sb["bgm"]["file"]
        for cand in (ep_dir / f, ROOT / "public" / f):
            if cand.exists():
                bgm = {"src": rel(cand).removeprefix("public/"), "volume": float(sb["bgm"].get("volume", 0.08))}
                break
        else:
            print(f"注意：没找到背景音乐 {f}，本次不加 BGM")

    ep_dir.mkdir(parents=True, exist_ok=True)
    narration = ep_dir / "narration.wav"
    audio_key = hashlib.sha1(json.dumps([SAMPLE_RATE, TARGET_LUFS, TRUE_PEAK, voice, rate, plan],
                                        ensure_ascii=False).encode("utf-8")).hexdigest()
    stamp = NARRATION_CACHE / f"{episode}.json"
    if narration_current(narration, stamp, audio_key):
        print("配音没有改动，沿用上次的 narration.wav")
    else:
        write_narration(narration, plan, voice, rate)
        loudness = normalize_loudness(narration)
        if loudness is not None:
            # 成片由 Remotion 输出为双声道（两个声道都是这条配音），实测响度比单声道高约 3 LU
            print(f"配音响度：{loudness[0]:.1f} LUFS → {loudness[1]:.1f} LUFS（成片为双声道，约 {loudness[1] + 3:.0f} LUFS）")
            NARRATION_CACHE.mkdir(parents=True, exist_ok=True)
            st = narration.stat()
            write_json(stamp, {"key": audio_key, "size": st.st_size, "mtime": st.st_mtime_ns})

    timeline = {
        "version": 1, "episode": episode,
        "title": sb.get("title", ""), "subtitle": sb.get("subtitle", ""),
        "width": width, "height": height, "fps": fps, "duration": round(total, 3),
        "audio": f"episodes/{episode}/narration.wav", "bgm": bgm,
        "scenes": scenes_out, "captions": captions, "lines": lines_out,
    }
    write_json(ep_dir / "timeline.json", timeline)

    with open(ep_dir / "captions.srt", "w", encoding="utf-8") as f:
        for i, c in enumerate(captions, 1):
            f.write(f"{i}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}\n\n")

    # ---- 出图提示词 + 图片检查
    durations = {s["id"]: s["end"] - s["start"] for s in scenes_out}
    by_id = {sc["id"]: sc for sc in sb["scenes"]}
    image_scenes = [sc for sc in sb["scenes"] if sc.get("type") != "chapter"]
    need = [sc for sc in image_scenes if not sc.get("reuse")]
    have = [sc for sc in need if find_image(ep_dir, episode, sc["id"])]
    warnings: list[str] = []
    for sc in have:
        img = find_image(ep_dir, episode, sc["id"])
        size = probe_size(ROOT / "public" / img) if img else None
        if size:
            ratio = (size[0] / size[1]) / (width / height)
            if abs(ratio - 1) > 0.15:
                warnings.append(f"{sc['id']} 图片比例 {size[0]}x{size[1]} 与视频 {aspect} 差别较大，会被明显裁切")
            elif min(size) < 0.6 * min(width, height):
                warnings.append(f"{sc['id']} 图片分辨率 {size[0]}x{size[1]} 偏低，画面可能发糊")
    negative = sb.get("negativePrompt", DEFAULT_NEGATIVE)
    cast = sb.get("cast") or {}
    cast_dir = ep_dir / "images" / CAST_DIR
    md = [
        f"# {sb.get('title', '')} · 出图提示词",
        "",
        "> 本文件由 `npm run voice -- " + episode + "` 自动生成，修改提示词请改 storyboard.json。",
        "",
        f"- 进度：需要 {len(need)} 张图，已有 {len(have)} 张，还差 {len(need) - len(have)} 张",
        f"- 画面比例：{aspect}（建议 {width}×{height} 或更高分辨率）",
        f"- 统一画风（已拼在每条提示词末尾）：{style}" if style.strip() else
        f"- 统一画风：还没有（imageStyle 是空的），运行 `npm run storyboard -- {episode} --style` 让大模型按内容推荐，或者自己填写",
        f"- 负面提示词（工具有「不希望出现」一栏时填写）：{negative}",
        f"- 自动出图：配置好 .env 后运行 `npm run images -- {episode}`，图片会自动命名并放进 images 文件夹",
        f"- 手动出图：按分镜编号命名（如 S01.png），放进 `public/episodes/{episode}/images/`，再重新运行 `npm run voice -- {episode}`",
        "- 建议先出 3–5 张试画风，满意后再批量出；图里不要有文字，字幕和标题由视频程序叠加",
        "",
    ]
    if cast:
        md += [
            "## 角色表",
            "",
            (f"自动出图时，会先给每个角色画一张定妆图，放在 `public/episodes/{episode}/images/{CAST_DIR}/`；"
             "之后有这个角色的画面，都会把定妆图作为参考图，让人物前后长得一样。"
             "手动出图时，如果工具支持上传参考图（垫图），把对应的定妆图一起传上去。"),
            "",
        ]
        for name, look in cast.items():
            sheet = find_cast_image(cast_dir, name)
            md += [f"### {name} · {f'定妆图 {CAST_DIR}/{sheet.name}' if sheet else '还没有定妆图'}", "",
                   "```text", cast_sheet_prompt(name, look, style), "```", ""]
    for sc in image_scenes:
        dur = durations.get(sc["id"], 0)
        lines_text = "".join(sc.get("lines", []))
        if sc.get("reuse"):
            md += [f"## {sc['id']} · {dur:.1f} 秒 · 复用 {sc['reuse']} 的图片（无需出图）", ""]
            continue
        status = "已有图片" if find_image(ep_dir, episode, sc["id"]) else "待出图"
        names = [n for n in dict.fromkeys(sc.get("cast", [])) if n in cast]
        refs = [f"角色：{'、'.join(names)}"] if names else []
        if sc.get("follow"):
            refs.append(f"延续 {sc['follow']} 的场景（出图时把它也作为参考图）")
        md += [
            f"## {sc['id']} · {dur:.1f} 秒 · {sc.get('visual') or '（画面待定）'} · {status}",
            "",
            f"> 台词：{lines_text}",
            "",
            *([" ｜ ".join(refs), ""] if refs else []),
            "```text",
            scene_prompt(sc.get("prompt", ""), [(n, cast[n]) for n in names], style, aspect),
            "```",
            "",
        ]
    (ep_dir / "prompts.md").write_text("\n".join(md), encoding="utf-8")
    (ep_dir / "images").mkdir(exist_ok=True)

    # ---- 注册到 Remotion
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    reg = json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.exists() else []
    reg = [e for e in reg if e.get("id") != episode] + [{"id": episode, "title": sb.get("title", "")}]
    write_json(REGISTRY, sorted(reg, key=lambda e: e["id"]))

    # ---- 汇总
    if verbose:
        print()
        print(f"分镜时长（共 {len(scenes_out)} 段）：")
        image_secs = [s["end"] - s["start"] for s in scenes_out if s["type"] == "image"]
        # 用 --images 减少张数时每张图本来就停得久，只提示明显比平均长的
        too_long = max(14.0, 1.6 * sum(image_secs) / len(image_secs)) if image_secs else 14.0
        for s in scenes_out:
            d = s["end"] - s["start"]
            if s["type"] == "chapter":
                print(f"  {s['id']:<4} {d:5.1f}s  [章节] {s['kicker']} {s['title']}")
                continue
            sc = by_id[s["id"]]
            tag = f"复用{sc['reuse']}" if sc.get("reuse") else ("代图" if s["id"] in filled else ("有图" if s["image"] else "缺图"))
            flag = "  <- 偏长，考虑拆分" if d > too_long else ("  <- 偏短" if d < 2.5 else "")
            print(f"  {s['id']:<4} {d:5.1f}s  [{tag}] {(sc.get('visual') or ''.join(sc.get('lines', []))[:18])}{flag}")
    for w in warnings:
        print(f"注意：{w}")
    no_prompt = [sc["id"] for sc in need if not (sc.get("prompt") or "").strip()]
    if no_prompt:
        print(f"注意：{len(no_prompt)} 个分镜还没写提示词（{', '.join(no_prompt[:6])}{' 等' if len(no_prompt) > 6 else ''}）")
    if not style.strip() and len(have) < len(need):
        print(f"注意：还没有画风（imageStyle 是空的），出图前运行 npm run storyboard -- {episode} --style 让大模型按内容推荐，"
              "或者自己填写")
    if filled:
        print(f"注意：{len(filled)} 个分镜没有图片，暂时用相邻画面的图片代替：{', '.join(filled)}")
    print()
    print(f"总时长 {int(total // 60)} 分 {total % 60:.1f} 秒，{len(captions)} 条字幕，图片 {len(have)}/{len(need)}")
    if verbose:
        print(f"已生成：{rel(ep_dir / 'narration.wav')}、timeline.json、captions.srt、prompts.md")
        if len(have) < len(need):
            print(f"出图：按 prompts.md 手动出图，或配置 .env 后运行 npm run images -- {episode}")
        print("下一步：npm run dev 预览；满意后 npm run render -- ep" + episode)
    if stale_images:
        warn_stale_images(episode, stale_images)
    have_ids = {sc["id"] for sc in have}
    return {
        "duration": total,
        "need": len(need),
        "have": len(have),
        "missing": [sc["id"] for sc in need if sc["id"] not in have_ids],
        "no_prompt": no_prompt,
        "filled": filled,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="口播文案 → 配音 + 字幕 + 分镜时间线")
    parser.add_argument("episode", help="集数编号，例如 001")
    parser.add_argument("--script", help="文案 .md 路径（默认自动找根目录下以集数编号开头的 .md）")
    parser.add_argument("--redraft", action="store_true", help="按文案重新生成分镜草稿（覆盖 storyboard.json，旧文件备份）")
    parser.add_argument("--voice", default="zh-CN-YunyangNeural", help="生成新草稿时使用的音色")
    parser.add_argument("--rate", default="+5%", help="生成新草稿时使用的语速，如 +5%% 或 -10%%")
    parser.add_argument("--aspect", default="9:16", choices=sorted(SIZES), help="生成新草稿时使用的画面比例")
    parser.add_argument("--images", type=int, help="生成新草稿时，整集只用这么多张图（不加就每 5–10 秒一张）")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]+", args.episode):
        die("集数编号只能包含字母、数字和 -（例如 001）")
    build(args.episode, args)


if __name__ == "__main__":
    main()
