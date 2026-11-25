# /// script
# requires-python = ">=3.10"
# dependencies = ["edge-tts>=7.2", "pypinyin>=0.55"]
# ///
"""一键生成：文案 → 分镜 → 配音 → 出图 → 导出视频，中途不需要人工操作。

    npm run make -- 002                    用 texts/ 里 002 开头的文案做出 out/002.mp4 和封面 out/002-cover.jpg
    npm run make -- 002 --provider ark     指定生图平台
    npm run make -- 002 --max-cost 30      出图费用上限（默认 20 元）
    npm run make -- 002 --images 20        新写分镜时整集只用 20 张图
    npm run make -- 002 --no-refs          出图不带参考图，角色外貌只用文字描述

已经完成的步骤会跳过（已有分镜、已有图片），中途中断后重新运行即可接着做。
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_episode as be  # noqa: E402
import gen_images as gi  # noqa: E402
import gen_storyboard as gs  # noqa: E402
import make_cover as mc  # noqa: E402
from api_common import llm_settings, missing_llm_vars  # noqa: E402
from envfile import load_env  # noqa: E402

REMOTION_CLI = mc.REMOTION_CLI


def stage(n: int, title: str) -> None:
    print(f"\n========== [{n}/4] {title} ==========", flush=True)


def image_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        episode=args.episode, provider=args.provider, only=None, pilot=0, force=False, compare=False,
        yes=True, dry_run=False, auto_fix=True, max_cost=args.max_cost, workers=args.workers,
        keep_png=False, rebuild=False, no_refs=args.no_refs,
    )


def build_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(script=args.script, redraft=False, voice=args.voice, rate=args.rate, aspect=args.aspect)


def missing_images(episode: str) -> list[dict]:
    ep_dir = be.EPISODES_DIR / episode
    sb = be.load_storyboard(ep_dir / "storyboard.json")
    be.validate(sb)
    return [sc for sc in sb["scenes"] if sc.get("type") != "chapter" and not sc.get("reuse")
            and not be.find_image(ep_dir, episode, sc["id"])]


def check_prompts(episode: str, missing: list[dict]) -> None:
    if missing and not any((sc.get("prompt") or "").strip() for sc in missing):
        be.die(
            f"分镜里还没有出图提示词（可能是 npm run voice 生成的草稿），没法自动出图。\n"
            f"  可以运行 npm run storyboard -- {episode} --force 让大模型重写分镜，或者让 AI 助手补上提示词，再重新运行。"
        )


def check_style(episode: str, missing: list[dict]) -> None:
    sb = be.load_storyboard(be.EPISODES_DIR / episode / "storyboard.json")
    if missing and not (sb.get("imageStyle") or "").strip():
        be.die(
            f"分镜里还没有画风（imageStyle 是空的），没法出图。\n"
            f"  运行 npm run storyboard -- {episode} --style 让大模型按内容推荐一个，或者自己填写，再重新运行。"
        )


def file_duration(path: Path) -> float | None:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                             capture_output=True, text=True, check=True).stdout.strip()
        return float(out)
    except (subprocess.CalledProcessError, ValueError):
        return None


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="一键生成：文案 → 分镜 → 配音 → 出图 → 导出视频")
    parser.add_argument("episode", help="集数编号，例如 002")
    parser.add_argument("--script", help="文案 .md 路径（默认自动找 texts/ 里以集数编号开头的 .md）")
    parser.add_argument("--provider", help="生图平台：bailian 或 ark，默认读 .env 的 IMAGE_PROVIDER")
    parser.add_argument("--max-cost", type=float, default=20.0, help="出图费用上限（元），预计超过时在花钱前停止，默认 20")
    parser.add_argument("--output", help="成片保存位置，默认 out/<集数>.mp4")
    parser.add_argument("--workers", type=int, default=2, help="出图时同时请求的数量（默认 2）")
    parser.add_argument("--no-refs", action="store_true",
                        help="出图时不带参考图（角色定妆图、上一格画面），角色外貌只用文字描述")
    parser.add_argument("--voice", default="zh-CN-YunyangNeural", help="新写分镜时使用的配音音色")
    parser.add_argument("--rate", default="+5%", help="新写分镜时使用的语速，如 +5%% 或 -10%%")
    parser.add_argument("--aspect", default="9:16", choices=sorted(be.SIZES), help="新写分镜时使用的画面比例")
    parser.add_argument("--images", type=int, help="新写分镜时，整集只用这么多张图（不加就每 5–10 秒一张）")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]+", args.episode):
        be.die("集数编号只能包含字母、数字和 -（例如 002）")

    load_env(be.ROOT)
    started = time.time()
    episode = args.episode
    sb_path = be.EPISODES_DIR / episode / "storyboard.json"
    output = Path(args.output).resolve() if args.output else be.ROOT / "out" / f"{episode}.mp4"

    # ---- 预检：在花钱之前，把能检查的都检查一遍
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        be.die("没有找到 ffmpeg，请先安装（winget install Gyan.FFmpeg）")
    node = shutil.which("node")
    if not node:
        be.die("没有找到 Node.js，请先安装（winget install OpenJS.NodeJS.LTS），装完重新打开终端")
    if not REMOTION_CLI.exists():
        be.die("还没有安装依赖：请先在项目文件夹里运行 npm install")
    need_storyboard = not sb_path.exists()
    md_path = gs.find_md(episode, args.script) if need_storyboard else None
    if need_storyboard and llm_settings() is None:
        be.die(f"第 {episode} 集还没有分镜，需要大模型来写：请在 .env 里填写 {'、'.join(missing_llm_vars())}。\n"
               "  也可以先让 AI 助手写好分镜，再运行这个命令。")
    missing = [] if need_storyboard else missing_images(episode)
    check_prompts(episode, missing)
    check_style(episode, missing)
    if need_storyboard or missing:
        gi.pick_providers(image_args(args))
    if llm_settings() is None:
        print("提示：没有配置大模型，出图被内容审核拦下时不会自动改写提示词")

    stage(1, "写分镜")
    stale_images = 0
    if need_storyboard:
        stale_images = gs.create_storyboard(episode, md_path, args.voice, args.rate, args.aspect, args.images)
        check_style(episode, missing_images(episode))
    else:
        redo = f"npm run storyboard -- {episode} --force" + (f" --images {args.images}" if args.images is not None else "")
        print(f"已有分镜 {be.rel(sb_path)}，跳过{'（--images 只在新写分镜时生效）' if args.images is not None else ''}。"
              f"想让大模型重写，先运行 {redo}")

    stage(2, "配音、字幕、时间线")
    be.build(episode, build_args(args), verbose=False)

    stage(3, "出图")
    missing = missing_images(episode)
    check_prompts(episode, missing)
    images_result = {"done": 0, "failed": [], "fixed": [], "cost": 0.0, "spent": 0.0}
    if missing:
        images_result = gi.run(image_args(args))
    else:
        print("所有分镜都已经有图片，跳过")

    stage(4, "导出视频")
    info = be.build(episode, build_args(args), verbose=False, fill_missing=True)
    if info["need"] and not info["have"]:
        be.die("一张图片都没有生成成功，已停止，没有导出视频。请检查上面的出图报错")
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"正在导出 {be.rel(output)}（7 分钟的视频大约需要 5 分钟）…", flush=True)
    result = subprocess.run([node, str(REMOTION_CLI), "render", f"ep{episode}", str(output)], cwd=be.ROOT)
    if result.returncode != 0 or not output.exists():
        be.die("导出视频失败，请查看上面的报错信息")
    cover = output.with_name(f"{output.stem}-cover.jpg")
    if not mc.render_cover(episode, cover, node):
        print(f"注意：封面生成失败（视频不受影响），可以稍后运行 npm run cover -- {episode} 重试")
        cover = None

    minutes = (time.time() - started) / 60
    duration = file_duration(output)
    print("\n========== 完成 ==========")
    print(f"成片：{be.rel(output)}（{output.stat().st_size / 1024 / 1024:.0f} MB"
          + (f"，时长 {int(duration // 60)} 分 {duration % 60:.0f} 秒" if duration else "") + "）")
    if cover:
        print(f"封面：{be.rel(cover)}")
    print(f"用时：{minutes:.1f} 分钟")
    if images_result["done"]:
        cost = f"，约 {images_result['spent']:.2f} 元" if images_result["spent"] else ""
        sheets = f"（另画了 {images_result['sheets']} 张角色定妆图）" if images_result.get("sheets") else ""
        print(f"本次出图：{images_result['done']} 张{sheets}{cost}（参考值，以平台账单为准）")
    if images_result["fixed"]:
        print(f"提示词被大模型改写后才通过审核的分镜：{', '.join(images_result['fixed'])}")
    if info["filled"]:
        ids = ",".join(info["filled"])
        no_refs = " --no-refs" if args.no_refs else ""
        print(f"注意：{', '.join(info['filled'])} 没能生成图片，成片里暂时用了相邻画面。"
              f"修改这些分镜的 prompt 后，运行 npm run images -- {episode} --only {ids}{no_refs}，再运行 npm run render -- ep{episode}")
    if stale_images:
        be.warn_stale_images(episode, stale_images)


if __name__ == "__main__":
    main()
