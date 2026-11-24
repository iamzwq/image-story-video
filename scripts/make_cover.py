# /// script
# requires-python = ">=3.10"
# dependencies = ["edge-tts>=7.2", "pypinyin>=0.55"]
# ///
"""生成视频封面：视频第一个画面 + 黑底白字的标题栏（样式在 src/Cover.tsx，npm run dev 里可以预览）。

    npm run cover -- 002                       输出 out/002-cover.jpg
    npm run cover -- 002 --output cover.jpg    指定保存位置（.jpg 或 .png）

封面直接用图片生成，不需要先导出视频；改了标题或第一张图后重新运行即可。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_episode as be  # noqa: E402

REMOTION_CLI = be.ROOT / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"


def default_output(episode: str) -> Path:
    return be.ROOT / "out" / f"{episode}-cover.jpg"


def render_cover(episode: str, output: Path, node: str) -> bool:
    """渲染封面，成功返回 True。调用前需要已经运行过 npm run voice（有 timeline.json）。"""
    timeline = json.loads((be.EPISODES_DIR / episode / "timeline.json").read_text(encoding="utf-8"))
    images = [s for s in timeline["scenes"] if s.get("type") == "image"]
    first = next((s for s in images if s.get("image")), None)
    if first is None:
        print("注意：还没有任何图片，封面只有标题和纯色背景")
    elif images[0] is not first:
        print(f"注意：{images[0]['id']} 还没有图片，封面背景暂时用了 {first['id']} 的图片")
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"正在生成封面 {be.rel(output)}…", flush=True)
    result = subprocess.run([node, str(REMOTION_CLI), "still", f"ep{episode}-cover", str(output), "--jpeg-quality=92"],
                            cwd=be.ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode != 0 or not output.exists():
        print((result.stdout + result.stderr).strip()[-2000:], file=sys.stderr)
        return False
    return True


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="生成视频封面：第一个画面 + 黑底白字标题")
    parser.add_argument("episode", help="集数编号，例如 002")
    parser.add_argument("--output", help="封面保存位置（.jpg 或 .png），默认 out/<集数>-cover.jpg")
    args = parser.parse_args()

    node = shutil.which("node")
    if not node:
        be.die("没有找到 Node.js，请先安装（winget install OpenJS.NodeJS.LTS），装完重新打开终端")
    if not REMOTION_CLI.exists():
        be.die("还没有安装依赖：请先在项目文件夹里运行 npm install")
    if not (be.EPISODES_DIR / args.episode / "timeline.json").exists():
        be.die(f"第 {args.episode} 集还没有时间线：请先运行 npm run voice -- {args.episode}")
    output = Path(args.output).resolve() if args.output else default_output(args.episode)
    if output.suffix.lower() not in (".jpg", ".jpeg", ".png"):
        be.die("封面只能保存为 .jpg 或 .png")
    if not render_cover(args.episode, output, node):
        be.die("生成封面失败，请查看上面的报错信息")
    print(f"已生成封面：{be.rel(output)}")


if __name__ == "__main__":
    main()
