# /// script
# requires-python = ">=3.10"
# dependencies = ["edge-tts>=7.2"]
# ///
"""用大模型把口播文案写成分镜（storyboard.json），然后自动配音、生成时间线和出图提示词。

    npm run storyboard -- 002            读取根目录下以 002 开头的 .md 文案
    npm run storyboard -- 002 --force    已有分镜时重新生成（旧文件备份为 storyboard.bak.json）

大模型在 .env 里配置（LLM_BASE_URL / LLM_API_KEY / LLM_MODEL），任何兼容 OpenAI 协议的服务都可以。
模型只决定「哪几句合成一个画面」和每个画面的描述、提示词，台词原文由脚本保留，不会被改写。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_episode as be  # noqa: E402
from api_common import ApiError, LLMError, chat, llm_settings, missing_llm_vars  # noqa: E402
from envfile import env, load_env  # noqa: E402

MOTIONS = {"zoomIn", "zoomOut", "panLeft", "panRight", "panUp", "panDown"}
CHUNK_LINES = 24  # 每次请求最多发送的句子数，长章节会拆成几次

SYSTEM_PROMPT = """你是短视频分镜师，负责把口播文案拆成画面。视频形式是「AI 配音 + 静态插画 + 字幕」，每个画面是一张 AI 生成的插画，播放时镜头会缓慢推拉。

任务：把编号的句子按顺序分组，每组对应一个画面，并为每个画面写画面说明和出图提示词。

分组规则：
1. 只能把相邻的句子分在一组，按顺序覆盖全部句子，不能遗漏、重复或打乱。
2. 每组总时长尽量在 5–10 秒，最长不超过 13 秒；话题转折的地方换画面。
3. 一句话不能拆开。

每个画面的字段：
- from、to：这组起止句子的编号（包含两端）。
- visual：画面说明，不超过 10 个字。
- prompt：中文出图提示词，40–90 字，只描述画面内容：主体、动作、场景、时代细节（服饰、建筑、器物要符合对应的历史时期）、景别构图、光线氛围。不要写画风和画面比例（会统一追加）。画面里不能出现文字、字母、标语、牌匾、印章；台词里的抽象概念要转化成具体可见的场景或象征物。
- motion：镜头运动，从 zoomIn、zoomOut、panLeft、panRight、panUp、panDown 中选一个：大场面、俯瞰宜 zoomOut 或平移，人物和细节宜 zoomIn，高耸的事物或上下层级宜 panUp。
- reuse（可选）：只有在明确回顾前面已经出现过的内容时，才填「已有画面」里的编号，这时可以不写 prompt。

只输出 JSON，不要输出解释，格式：
{"scenes":[{"from":1,"to":2,"visual":"……","prompt":"……","motion":"zoomIn"},{"from":3,"to":3,"visual":"……","reuse":"S05","motion":"panLeft"}]}

示例（另一期视频的片段）：
1. [3.4s] 真正改变人类社会的，是农业的出现。
2. [4.2s] 大约一万年前，人类开始种植农作物、驯养动物。
3. [6.0s] 这意味着，人类不再需要每天四处寻找食物，而是可以在一个地方长期生活。
4. [3.1s] 人口开始增加，村庄逐渐形成。
输出：
{"scenes":[{"from":1,"to":2,"visual":"农业出现","prompt":"约一万年前的黄河流域，新石器时代的先民在田里播种粟，手持石锄和石镰，旁边有驯养的猪和狗，温暖的晨光","motion":"zoomIn"},{"from":3,"to":4,"visual":"定居的村落","prompt":"仰韶文化风格的定居村落：半地穴式圆形茅草屋，屋顶升起炊烟，妇女在门前制作彩陶，孩子与家犬嬉戏，村子周围是成片的粟田","motion":"panRight"}]}"""


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


def check_groups(obj, n: int, known: set[str]) -> list[dict]:
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
                    "prompt": prompt, "reuse": reuse, "motion": motion})
        expected = end + 1
    if expected != n + 1:
        raise PlanError(f"第 {expected}–{n} 句没有被分组")
    return out


def fallback_groups(lines: list[tuple[str, float]]) -> list[dict]:
    groups, start, dur = [], 1, 0.0
    for i, (_, d) in enumerate(lines, 1):
        if i > start and (dur >= be.SCENE_TARGET or dur + d > be.SCENE_MAX):
            groups.append({"from": start, "to": i - 1, "visual": "", "prompt": "", "reuse": "", "motion": None})
            start, dur = i, 0.0
        dur += d + be.DEFAULT_PAUSES["line"]
    groups.append({"from": start, "to": len(lines), "visual": "", "prompt": "", "reuse": "", "motion": None})
    return groups


def plan_chunk(cfg, ctx: str, section: str, lines: list[tuple[str, float]], known: list[tuple[str, str]],
               warnings: list[str]) -> list[dict]:
    listing = "\n".join(f"{i}. [{d:.1f}s] {t}" for i, (t, d) in enumerate(lines, 1))
    existing = "，".join(f"{sid} {vis}" for sid, vis in known) or "无"
    user = f"{ctx}\n\n当前段落：{section}\n已有画面（可以复用）：{existing}\n\n请为下面 {len(lines)} 句分组（编号只在本段内有效）：\n{listing}"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
    last_error = ""
    for _ in range(2):
        content = ""
        try:
            content = ask(cfg, messages)
            return check_groups(extract_json(content), len(lines), {sid for sid, _ in known})
        except PlanError as err:
            last_error = str(err)
            if content:
                messages += [{"role": "assistant", "content": content},
                             {"role": "user", "content": f"上面的输出有问题：{err}。请按要求重新输出完整的 JSON。"}]
    if len(lines) > 4:
        half = len(lines) // 2
        return plan_chunk(cfg, ctx, section, lines[:half], known, warnings) + [
            {**g, "from": g["from"] + half, "to": g["to"] + half}
            for g in plan_chunk(cfg, ctx, section, lines[half:], known, warnings)
        ]
    warnings.append(f"「{section}」有 {len(lines)} 句没能让模型分好（{last_error}），已按时长自动分组，提示词需要补写")
    return fallback_groups(lines)


def create_storyboard(episode: str, md_path: Path, voice: str, rate: str, aspect: str) -> int:
    """配音（用于统计时长）→ 大模型分组写提示词 → 写入 storyboard.json。返回原本就在 images 里的图片数。"""
    cfg = require_llm()
    ep_dir = be.EPISODES_DIR / episode
    sb_path = ep_dir / "storyboard.json"
    pieces = be.script_pieces(md_path)
    be.synth_all([t for _, ts in pieces for t in ts], voice, rate)

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
            current += [(t, be.line_duration(t, voice, rate)) for t in texts]
    sections.append((name, chapter_unit, current))

    title, subtitle = be.titles_from_filename(md_path)
    full_text = "\n".join(t for _, ts in pieces for t in ts)
    ctx = f"视频标题：{title}{'——' + subtitle if subtitle else ''}\n完整文案（只用来理解上下文）：\n{full_text[:8000]}"
    total_calls = sum(math.ceil(len(lines) / CHUNK_LINES) for _, _, lines in sections if lines)
    print(f"正在用 {env('LLM_MODEL')} 写分镜（共 {total_calls} 段，每段通常需要 10–60 秒）…")

    scenes: list[dict] = []
    known: list[tuple[str, str]] = []
    warnings: list[str] = []
    n_img = n_ch = call = 0
    for name, chapter, lines in sections:
        if chapter:
            n_ch += 1
            scenes.append(be.chapter_scene(n_ch, chapter["unit"], chapter["texts"]))
        if not lines:
            continue
        parts = math.ceil(len(lines) / CHUNK_LINES)
        size = math.ceil(len(lines) / parts)
        for k in range(parts):
            chunk = lines[k * size:(k + 1) * size]
            call += 1
            started = time.time()
            groups = plan_chunk(cfg, ctx, name, chunk, known, warnings)
            for g in groups:
                n_img += 1
                sid = f"S{n_img:02d}"
                scene: dict = {"id": sid}
                if g["reuse"]:
                    scene["reuse"] = g["reuse"]
                scene["visual"] = g["visual"]
                if not g["reuse"]:
                    scene["prompt"] = g["prompt"]
                if g["motion"]:
                    scene["motion"] = g["motion"]
                scene["lines"] = [t for t, _ in chunk[g["from"] - 1:g["to"]]]
                scenes.append(scene)
                if not g["reuse"] and g["visual"]:
                    known.append((sid, g["visual"]))
            print(f"  [{call}/{total_calls}] {name}：{len(chunk)} 句 → {len(groups)} 个画面（{time.time() - started:.0f} 秒）")

    ep_dir.mkdir(parents=True, exist_ok=True)
    stale_images = be.count_images(ep_dir)
    if sb_path.exists():
        shutil.copyfile(sb_path, ep_dir / "storyboard.bak.json")
        print("旧分镜已备份为 storyboard.bak.json")
    be.write_json(sb_path, be.new_storyboard(md_path, voice, rate, aspect, scenes))
    images = [s for s in scenes if s.get("type") != "chapter"]
    reused = sum(1 for s in images if s.get("reuse"))
    print(f"已写好分镜：{be.rel(sb_path)}（{len(images)} 个画面，其中 {reused} 个复用前面的图，需要出图 {len(images) - reused} 张）")
    for w in warnings:
        print(f"注意：{w}")
    return stale_images


def find_md(episode: str, script: str | None) -> Path:
    md_path = be.find_script(episode, script)
    if md_path is None or not md_path.exists():
        be.die(f"没找到第 {episode} 集的文案：请把文案放在项目根目录，文件名以 {episode} 开头，或用 --script 指定")
    return md_path


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="用大模型把口播文案写成分镜")
    parser.add_argument("episode", help="集数编号，例如 002")
    parser.add_argument("--script", help="文案 .md 路径（默认自动找根目录下以集数编号开头的 .md）")
    parser.add_argument("--force", action="store_true", help="已有 storyboard.json 时重新生成（旧文件会备份）")
    parser.add_argument("--voice", default="zh-CN-YunyangNeural", help="配音音色")
    parser.add_argument("--rate", default="+5%", help="语速，如 +5%% 或 -10%%")
    parser.add_argument("--aspect", default="9:16", choices=sorted(be.SIZES), help="画面比例")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]+", args.episode):
        be.die("集数编号只能包含字母、数字和 -（例如 002）")

    load_env(be.ROOT)
    require_llm()
    sb_path = be.EPISODES_DIR / args.episode / "storyboard.json"
    if sb_path.exists() and not args.force:
        be.die(f"{be.rel(sb_path)} 已经存在。要用 AI 重新生成请加 --force（旧文件会备份为 storyboard.bak.json）")
    md_path = find_md(args.episode, args.script)
    if not shutil.which("ffmpeg"):
        be.die("没有找到 ffmpeg，请先安装（例如 winget install Gyan.FFmpeg）")

    stale_images = create_storyboard(args.episode, md_path, args.voice, args.rate, args.aspect)
    be.build(args.episode, argparse.Namespace(script=args.script, redraft=False, voice=args.voice,
                                              rate=args.rate, aspect=args.aspect))
    print(f"建议先打开 public/episodes/{args.episode}/prompts.md 看一遍画面描述，不满意的地方可以直接改 storyboard.json 或让 AI 改。")
    if stale_images:
        be.warn_stale_images(args.episode, stale_images)


if __name__ == "__main__":
    main()
