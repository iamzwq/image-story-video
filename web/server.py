# /// script
# requires-python = ">=3.10"
# dependencies = ["edge-tts>=7.2", "pypinyin>=0.55"]
# ///
"""网页版：在浏览器里新建视频、写分镜、出图、预览和导出，设置页填写大模型和生图平台的 API Key。

    npm run web                    构建网页并启动，然后在浏览器里打开 http://127.0.0.1:3100
    npm run web -- --port 3200     换一个端口
    npm run web -- --no-open       不自动打开浏览器

网页是给现有脚本加的界面：写分镜、配音、出图、导出都在后台运行 scripts/ 里的同一套命令（一次运行一个，其余排队），
设置页的内容保存在项目根目录的 .env。网页没有登录，默认只允许本机访问。
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import ipaddress
import itertools
import json
import os
import queue
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

import edge_tts

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_episode as be  # noqa: E402
import gen_images as gi  # noqa: E402
from api_common import ApiError, LLMError, chat, chat_endpoint  # noqa: E402
from envfile import read_env  # noqa: E402

DIST_DIR = ROOT / "web" / "dist"
PUBLIC_DIR = ROOT / "public"
OUT_DIR = ROOT / "out"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
REMOTION_CLI = ROOT / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
UV = shutil.which("uv")
NODE = shutil.which("node")

SETTING_KEYS = (
    "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "IMAGE_PROVIDER",
    "DASHSCOPE_API_KEY", "DASHSCOPE_IMAGE_MODEL", "DASHSCOPE_BASE_URL",
    "ARK_API_KEY", "ARK_IMAGE_MODEL", "ARK_BASE_URL",
)
SECRET_KEYS = {"LLM_API_KEY", "DASHSCOPE_API_KEY", "ARK_API_KEY"}
# 接口地址和它的 Key：换了地址就要重新填 Key，免得把原来的 Key 发给别的网站
KEY_FOR_URL = {"LLM_BASE_URL": "LLM_API_KEY", "ARK_BASE_URL": "ARK_API_KEY", "DASHSCOPE_BASE_URL": "DASHSCOPE_API_KEY"}
LLM_KEYS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")
# 设置页列出的生图模型（也可以填其他模型名），单价和是否支持参考图取自 gen_images.py
MODEL_CHOICES = {
    "bailian": ("DASHSCOPE_IMAGE_MODEL", ["z-image-turbo", "qwen-image-3.0", "qwen-image-3.0-pro", "qwen-image-2.1-turbo"]),
    "ark": ("ARK_IMAGE_MODEL", ["doubao-seedream-5-5-261028", "doubao-seedream-5-0-flash-260915"]),
}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
EP_RE = re.compile(r"[A-Za-z0-9-]+")
VOICE_RE = re.compile(r"[a-z]{2,3}-[A-Z]{2}(?:-[A-Za-z]+)?-[A-Za-z]+Neural")
RATE_RE = re.compile(r"[+-]\d{1,3}%")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
# Remotion 不在终端里运行时每渲染一帧打印一行进度，日志里每秒只留一行
PROGRESS_RE = re.compile(r"(Rendered|Rendering|Encoded|Encoding|Stitched|Stitching)\D*?(\d+)\s*/\s*(\d+)")
MOTION_NAMES = set(be.MOTIONS)
MAX_LOG_LINES = 4000
BUSY = "这一集正在运行任务，等任务结束后再试"
# 标题会写进文案的文件名：把文件名里不能用的符号换成全角
FILENAME_SAFE = str.maketrans({"\\": "＼", "/": "／", ":": "：", "*": "＊", "?": "？", '"': "＂", "<": "《", ">": "》", "|": "｜"})
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".md": "text/markdown; charset=utf-8",
    ".srt": "application/x-subrip; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".webp": "image/webp", ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
    ".mp4": "video/mp4", ".otf": "font/otf", ".ttf": "font/ttf", ".woff2": "font/woff2", ".ico": "image/x-icon",
}
SAMPLE_TEXT = "这是配音试听。一篇文案配上插画和字幕，就能做成一条口播视频。"


class HttpError(Exception):
    def __init__(self, status: int, message: str, code: str = "") -> None:
        super().__init__(message)
        self.status, self.message, self.code = status, message, code


OUTPUT_LOCK = threading.Lock()


def call_quietly(fn: Callable, *args):
    """在网页进程里调用脚本的函数：不打印它的提示；它出错退出（be.die）时把原因转成 HttpError。"""
    err = io.StringIO()
    with OUTPUT_LOCK, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        try:
            return fn(*args)
        except SystemExit:
            message = err.getvalue().strip().removeprefix("错误：")
    raise HttpError(400, message or "操作失败")


def int_option(value, low: int, high: int, name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise HttpError(400, f"{name}要填整数") from None
    if not low <= number <= high:
        raise HttpError(400, f"{name}要在 {low} 到 {high} 之间")
    return number


def float_option(value, low: float, high: float, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise HttpError(400, f"{name}要填数字") from None
    if not low <= number <= high:  # NaN 也会被拦下
        raise HttpError(400, f"{name}要在 {low:g} 到 {high:g} 之间")
    return number


# ---------------------------------------------------------------- 设置（.env）


def effective_settings() -> dict[str, str]:
    """脚本实际会用的配置：系统环境变量里有值的优先，其次是 .env（和 envfile.load_env 的规则一样）。"""
    saved = read_env(ROOT)
    return {key: (os.environ.get(key) or "").strip() or saved.get(key, "") for key in SETTING_KEYS}


def choose_provider(settings: dict[str, str], name: str = "") -> gi.Provider:
    """按设置选出生图平台，选不出来时说明原因。"""
    found = gi.configured_providers(lambda key, default="": settings.get(key) or default)
    if not found:
        raise HttpError(400, "还没有填写生图平台的 API Key，请先到「设置」里填写", "settings")
    name = (name or settings.get("IMAGE_PROVIDER", "")).strip().lower()
    if name:
        key = gi.ALIASES.get(name)
        if key is None:
            raise HttpError(400, f"不认识的生图平台 {name}，请到「设置」里重新选择", "settings")
        if key not in found:
            raise HttpError(400, f"默认生图平台是{gi.LABELS[key]}，但还没有填写它的 API Key，请到「设置」里填写或换一个平台",
                            "settings")
        return found[key]
    if len(found) == 1:
        return next(iter(found.values()))
    raise HttpError(400, "两个生图平台都填了 API Key，请到「设置」里选择默认用哪个", "settings")


def has_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def readiness(settings: dict[str, str]) -> dict:
    image, image_error = None, ""
    try:
        image = choose_provider(settings).label
    except HttpError as err:
        image_error = err.message
    return {"llm": all(settings.get(k) for k in LLM_KEYS), "image": image, "imageError": image_error,
            "ffmpeg": has_ffmpeg()}


def model_info(model: str) -> dict:
    ref_price = gi.lookup(gi.INPUT_PRICES, model) or (0.0, 0)
    return {"id": model, "price": gi.estimate(model), "refs": gi.ref_limit(model),
            "refPrice": ref_price[0], "refFree": ref_price[1]}


def get_settings() -> dict:
    """设置页显示的内容。API Key 只返回末尾几位，不把完整的 Key 发给浏览器。"""
    saved = read_env(ROOT)
    settings = effective_settings()
    values = {}
    for key in SETTING_KEYS:
        value = saved.get(key, "")
        item: dict = {"set": bool(value), "override": bool((os.environ.get(key) or "").strip())}
        if key in SECRET_KEYS:
            item["hint"] = (f"…{value[-4:]}" if len(value) > 8 else "已填写") if value else ""
        else:
            item["value"] = value
        values[key] = item
    models = {}
    for provider, (var, choices) in MODEL_CHOICES.items():
        current = [settings[var]] if settings.get(var) else []
        models[provider] = [model_info(m) for m in dict.fromkeys([*choices, *current])]
    return {"values": values, "models": models, "ready": readiness(settings)}


def env_line(key: str, value: str) -> str:
    if value and (" #" in value or value[0] in "'\"" or value[-1] in "'\""):
        value = f"'{value}'" if '"' in value else f'"{value}"'
    return f"{key}={value}"


def save_settings(values) -> None:
    """把设置写进 .env：改动原有的行，保留其他内容和注释；还没有 .env 时以 .env.example 为模板。"""
    if not isinstance(values, dict):
        raise HttpError(400, "设置的格式不对")
    updates: dict[str, str] = {}
    for key, value in values.items():
        if key not in SETTING_KEYS or not isinstance(value, str):
            raise HttpError(400, f"不认识的设置项：{key}")
        value = value.strip()
        if "\n" in value or "\r" in value:
            raise HttpError(400, f"{key} 里不能有换行")
        if key.endswith("_BASE_URL") and value and not re.match(r"https?://", value):
            raise HttpError(400, "接口地址要以 http:// 或 https:// 开头")
        if key == "IMAGE_PROVIDER" and value not in ("", "bailian", "ark"):
            raise HttpError(400, "默认生图平台只能是 bailian 或 ark")
        updates[key] = value
    saved = read_env(ENV_FILE.parent)
    for url_key, key_key in KEY_FOR_URL.items():
        if (url_key in updates and updates[url_key].rstrip("/") != saved.get(url_key, "").rstrip("/")
                and saved.get(key_key) and key_key not in updates):
            raise HttpError(400, f"换了接口地址（{url_key}），请重新填写对应的 API Key（{key_key}），原来的 Key 不会发给新地址")
    source = ENV_FILE if ENV_FILE.exists() else ENV_EXAMPLE
    raw = source.read_bytes() if source.exists() else b""
    newline = "\r\n" if b"\r\n" in raw else "\n"  # 保留原来的换行符（read_text 会把 \r\n 统一成 \n）
    lines = raw.decode("utf-8-sig").splitlines()
    for key, value in updates.items():
        active = [i for i, s in enumerate(lines) if re.match(rf"\s*(?:export\s+)?{key}\s*=", s)]
        if active:
            lines[active[0]] = env_line(key, value)
            for i in reversed(active[1:]):  # 同一项写了好几次时只留一处，免得改了不生效
                del lines[i]
        elif value:
            commented = next((i for i, s in enumerate(lines) if re.match(rf"\s*#\s*{key}\s*=", s)), None)
            if commented is None:
                lines.append(env_line(key, value))
            else:
                lines[commented] = env_line(key, value)
    tmp = ENV_FILE.with_name(".env.tmp")
    tmp.write_text(newline.join(lines) + newline, encoding="utf-8", newline="")
    tmp.replace(ENV_FILE)


def test_llm(body: dict) -> dict:
    """用表单里填的（还没保存的）大模型配置发一句话试试。"""
    saved = effective_settings()
    base = str(body.get("LLM_BASE_URL") or "").strip()
    key = str(body.get("LLM_API_KEY") or "").strip()
    model = str(body.get("LLM_MODEL") or "").strip()
    if not key and base.rstrip("/") == saved["LLM_BASE_URL"].rstrip("/"):
        key = saved["LLM_API_KEY"]  # 没改 Key 就用已保存的；换了接口地址则要重新填，免得把 Key 发给别的网站
    if not base or not model:
        raise HttpError(400, "接口地址和模型都要填写")
    if not re.match(r"https?://", base):
        raise HttpError(400, "接口地址要以 http:// 或 https:// 开头")
    if not key:
        raise HttpError(400, "请填写 API Key")
    started = time.time()
    try:
        reply = chat((chat_endpoint(base), key, model),
                     [{"role": "user", "content": "这是连接测试，请只回复「收到」两个字。"}], timeout=30)
    except (ApiError, LLMError) as err:
        # 代理、网关出错时返回的是网页，只留下里面的文字
        return {"ok": False, "error": " ".join(re.sub(r"<[^>]*>", " ", str(err)).split())[:300]}
    return {"ok": True, "reply": reply[:60], "seconds": round(time.time() - started, 1)}


_voice_samples: dict[tuple[str, str], bytes] = {}


def voice_sample(voice: str, rate: str) -> bytes:
    if not VOICE_RE.fullmatch(voice) or not RATE_RE.fullmatch(rate):
        raise HttpError(400, "音色或语速的格式不对")
    if (voice, rate) not in _voice_samples:
        async def synth() -> bytes:
            audio = bytearray()
            async for chunk in edge_tts.Communicate(SAMPLE_TEXT, voice, rate=rate).stream():
                if chunk["type"] == "audio":
                    audio.extend(chunk["data"])
            return bytes(audio)

        try:
            data = asyncio.run(synth())
        except Exception as err:  # edge-tts 的网络错误类型很多
            raise HttpError(502, f"试听生成失败（配音服务需要联网）：{err}") from None
        if not data:
            raise HttpError(502, "试听生成失败：没有收到音频")
        _voice_samples[(voice, rate)] = data
    return _voice_samples[(voice, rate)]


# ---------------------------------------------------------------- 各集的状态


def episode_dir(ep: str) -> Path:
    return be.EPISODES_DIR / ep


def episode_ids() -> list[str]:
    """texts/（和旧位置项目根目录）里以数字开头的文案，加上已经有分镜的集。"""
    ids: set[str] = set()
    for folder in (be.SCRIPTS_DIR, ROOT):
        if folder.is_dir():
            for p in folder.glob("*.md"):
                m = re.match(r"\d+", p.stem)
                if m and p.is_file():
                    ids.add(m.group(0))
    if be.EPISODES_DIR.is_dir():
        for d in be.EPISODES_DIR.iterdir():
            if EP_RE.fullmatch(d.name) and (d / "storyboard.json").is_file():
                ids.add(d.name)
    return sorted(ids)


def next_episode_id() -> str:
    def taken(ep: str) -> bool:
        return (episode_dir(ep).exists() or (OUT_DIR / f"{ep}.mp4").exists()
                or any(next(folder.glob(f"{ep}*.md"), None) for folder in (be.SCRIPTS_DIR, ROOT)))

    n = max((int(ep) for ep in episode_ids() if ep.isdigit()), default=0) + 1
    while taken(f"{n:03d}"):
        n += 1
    return f"{n:03d}"


def check_episode(ep: str) -> None:
    if not EP_RE.fullmatch(ep) or ep not in episode_ids():
        raise HttpError(404, f"找不到第 {ep} 集")


def load_storyboard(ep: str) -> tuple[dict | None, str]:
    path = episode_dir(ep) / "storyboard.json"
    if not path.exists():
        return None, ""
    try:
        sb = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as err:
        return None, f"storyboard.json 格式有误：{err}"
    if not isinstance(sb, dict) or not isinstance(sb.get("scenes"), list):
        return None, "storyboard.json 里没有 scenes"
    return sb, ""


def image_scenes(sb: dict) -> list[dict]:
    return [sc for sc in sb["scenes"] if isinstance(sc, dict) and sc.get("id") and sc.get("type") != "chapter"]


def public_url(rel: str) -> str:
    """public/ 里的文件的网址，带上修改时间作版本号：文件改了网址就变，浏览器不会用旧的缓存。"""
    try:
        version = (PUBLIC_DIR / rel).stat().st_mtime_ns
    except OSError:
        version = 0
    return f"/{quote(rel)}?v={version}"


def mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def out_file(name: str) -> dict | None:
    path = OUT_DIR / name
    if not path.is_file():
        return None
    st = path.stat()
    return {"name": name, "url": f"/out/{quote(name)}?v={st.st_mtime_ns}", "size": st.st_size, "mtime": st.st_mtime}


def summary(ep: str) -> dict:
    ep_dir = episode_dir(ep)
    script = be.find_script(ep, None)
    title, subtitle = be.titles_from_filename(script) if script else (f"第 {ep} 集", "")
    sb, error = load_storyboard(ep)
    need = have = 0
    draft = has_style = False
    if sb:
        title, subtitle = str(sb.get("title") or title), str(sb.get("subtitle") or "")
        todo = [sc for sc in image_scenes(sb) if not sc.get("reuse")]
        need = len(todo)
        have = sum(1 for sc in todo if be.find_image(ep_dir, ep, str(sc["id"])))
        draft = not any(str(sc.get("prompt") or "").strip() for sc in todo)
        has_style = bool(str(sb.get("imageStyle") or "").strip())
    duration = None
    with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
        duration = float(json.loads((ep_dir / "timeline.json").read_text(encoding="utf-8"))["duration"])
    video, cover = out_file(f"{ep}.mp4"), out_file(f"{ep}-cover.jpg")
    if video:
        # 成片之后又改过分镜、配音或图片，就不是最新的了
        images = ep_dir / "images"
        changed = [mtime(ep_dir / "storyboard.json"), mtime(ep_dir / "narration.wav")]
        if images.is_dir():
            changed += [mtime(p) for p in images.iterdir() if p.suffix.lower() in be.IMAGE_EXTS]
        video["stale"] = max(changed) > video["mtime"]
    if not sb:
        stage = "script"
    elif draft:
        stage = "draft"
    elif have < need:
        stage = "images"
    elif not video or video["stale"]:
        stage = "ready"
    else:
        stage = "done"
    job = jobs.latest(ep)
    return {
        "id": ep, "title": title, "subtitle": subtitle, "stage": stage, "hasScript": bool(script),
        "hasStoryboard": bool(sb), "storyboardError": error, "draft": draft, "hasStyle": has_style,
        "imageCount": {"need": need, "have": have}, "duration": duration, "video": video, "cover": cover,
        "job": jobs.public(job) if job else None,
    }


def detail(ep: str) -> dict:
    check_episode(ep)
    data = summary(ep)
    ep_dir = episode_dir(ep)
    script = be.find_script(ep, None)
    data["script"] = ({"name": script.name, "text": script.read_text(encoding="utf-8-sig")}
                      if script and script.is_file() else None)
    sb, _ = load_storyboard(ep)
    data["storyboard"] = sb
    data["options"] = saved_options(ep)
    scene_images: dict[str, dict] = {}
    cast_images: dict[str, str] = {}
    if sb:
        manifest = gi.read_json(ep_dir / "images" / "_generated.json")
        for sc in image_scenes(sb):
            sid = str(sc["id"])
            rel = be.find_image(ep_dir, ep, sid)
            if rel:
                made = manifest.get(sid) if isinstance(manifest.get(sid), dict) else {}
                scene_images[sid] = {"url": public_url(rel), "prompt": made.get("prompt"), "model": made.get("model")}
        cast = sb.get("cast") if isinstance(sb.get("cast"), dict) else {}
        for name in cast:
            sheet = be.find_cast_image(ep_dir / "images" / be.CAST_DIR, str(name))
            if sheet:
                cast_images[name] = public_url(be.rel(sheet).removeprefix("public/"))
    data["sceneImages"] = scene_images
    data["castImages"] = cast_images
    timeline, durations, version = None, {}, None
    tl_path = ep_dir / "timeline.json"
    with contextlib.suppress(OSError, ValueError):
        timeline = json.loads(tl_path.read_text(encoding="utf-8"))
        version = str(tl_path.stat().st_mtime_ns)
    if isinstance(timeline, dict):
        timeline.pop("lines", None)
        for s in timeline.get("scenes", []):
            if s.get("image"):
                s["image"] = public_url(s["image"])
            durations[s["id"]] = round(s["end"] - s["start"], 1)
        if timeline.get("audio"):
            timeline["audio"] = public_url(timeline["audio"])
        if isinstance(timeline.get("bgm"), dict) and timeline["bgm"].get("src"):
            timeline["bgm"]["src"] = public_url(timeline["bgm"]["src"])
    else:
        timeline = None
    data.update(timeline=timeline, timelineVersion=version, durations=durations)
    return data


def clean_title(value, name: str, required: bool) -> str:
    text = " ".join(str(value or "").split()).translate(FILENAME_SAFE).replace("——", "—").strip(" .")
    if required and not text:
        raise HttpError(400, f"请填写{name}")
    if len(text) > 60:
        raise HttpError(400, f"{name}太长了（最多 60 个字）")
    return text


def write_script(ep: str, body: dict, old: Path | None) -> None:
    """文案存为 texts/<集数>.标题——副标题.md，和手动放文案的规则一样。"""
    title = clean_title(body.get("title"), "标题", True)
    subtitle = clean_title(body.get("subtitle"), "副标题", False)
    # 统一成 \n：write_text 在 Windows 上会把 \n 写成 \r\n，原样写入 \r\n 会变成 \r\r\n，读出来行距翻倍
    text = str(body.get("text") or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        raise HttpError(400, "请填写文案")
    if len(text) > 200_000:
        raise HttpError(400, "文案太长了")
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / "script.md"
        probe.write_text(text, encoding="utf-8")
        if not any(u["kind"] == "line" for u in be.parse_script(probe)):
            raise HttpError(400, "文案里没有读到正文（标题、分隔线、网址这些不会读出来），请检查一下")
    be.SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    path = be.SCRIPTS_DIR / f"{ep}.{title}{'——' + subtitle if subtitle else ''}.md"
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    if old and old.exists() and not old.samefile(path):
        old.unlink()


def validate_storyboard(sb) -> None:
    if not isinstance(sb, dict) or not isinstance(sb.get("scenes"), list) or not all(
            isinstance(sc, dict) for sc in sb["scenes"]):
        raise HttpError(400, "分镜的格式不对")
    call_quietly(be.validate, sb)
    for key in ("title", "subtitle", "imageStyle", "negativePrompt", "voice", "rate"):
        if key in sb and not isinstance(sb[key], str):
            raise HttpError(400, f"{key} 必须是文字")
    if not VOICE_RE.fullmatch(sb.get("voice", "zh-CN-YunxiNeural")):
        raise HttpError(400, "音色的格式不对")
    if not RATE_RE.fullmatch(sb.get("rate", "+0%")):
        raise HttpError(400, "语速的格式不对，例如 +5%")
    pron = sb.get("pronunciation") or {}
    if not isinstance(pron, dict) or not all(isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip()
                                             for k, v in pron.items()):
        raise HttpError(400, "读音纠正的每一项都要填写原文和念法")
    for sc in sb["scenes"]:
        if not all(isinstance(t, str) and t.strip() for t in sc.get("lines", [])):
            raise HttpError(400, f"{sc['id']} 的台词里有空行")
        for key in ("visual", "prompt", "kicker", "title"):
            if key in sc and not isinstance(sc[key], str):
                raise HttpError(400, f"{sc['id']} 的 {key} 必须是文字")
        if sc.get("motion") and sc["motion"] not in MOTION_NAMES:
            raise HttpError(400, f"{sc['id']} 的镜头运动不对")


# ---------------------------------------------------------------- 出图费用预估


def image_selection(opts: dict, sb: dict) -> argparse.Namespace:
    """网页上的出图方式 → gen_images.py 的参数：pilot 试画、missing 缺图、all 全部重画、only 指定分镜。"""
    mode = str(opts.get("mode") or "missing")
    only, pilot = None, 0
    if mode == "pilot":
        pilot = int_option(opts.get("pilot", 4), 1, 20, "试画张数")
    elif mode == "only":
        ids = [x for x in re.split(r"[,\s]+", str(opts.get("ids") or "")) if x]
        known = {str(sc["id"]) for sc in image_scenes(sb)}
        if not ids or any(x not in known for x in ids):
            raise HttpError(400, "分镜编号不对")
        only = ",".join(dict.fromkeys(ids))
    elif mode not in ("missing", "all"):
        raise HttpError(400, "出图方式不对")
    return argparse.Namespace(mode=mode, only=only, pilot=pilot, force=mode == "all", compare=False)


def image_ready(ep: str, opts: dict) -> tuple[dict, gi.Provider, argparse.Namespace]:
    sb, error = load_storyboard(ep)
    if not sb:
        raise HttpError(400, error or "还没有分镜，先写分镜")
    call_quietly(be.validate, sb)
    if not str(sb.get("imageStyle") or "").strip():
        raise HttpError(400, "还没有画风，出图前先在「整体设置」里让 AI 推荐一个，或者自己填写", "style")
    provider = choose_provider(effective_settings(), str(opts.get("provider") or ""))
    return sb, provider, image_selection(opts, sb)


def estimate_images(ep: str, opts: dict) -> dict:
    """出图前的费用预估，算法和 gen_images.py 运行前显示的一样。"""
    check_episode(ep)
    sb, provider, selection = image_ready(ep, opts)
    ep_dir = episode_dir(ep)
    scenes = call_quietly(gi.select_scenes, sb, ep_dir, ep, selection)
    no_refs = str(opts.get("noRefs") or "") in ("1", "true", "True")
    limit = 0 if no_refs else gi.ref_limit(provider.model)
    cast = sb.get("cast") or {}
    dest = ep_dir / "images"
    sheets = gi.sheets_to_draw(scenes, cast, dest / be.CAST_DIR, sb["imageStyle"], limit)
    cost, counts = gi.plan_cost(provider.model, scenes, sheets, cast, limit, {sc["id"]: sc for sc in sb["scenes"]}, dest)
    return {"count": len(scenes), "ids": [sc["id"] for sc in scenes], "sheets": sheets, "refs": sum(counts),
            "cost": round(cost, 2), "priceKnown": gi.estimate(provider.model) is not None, "provider": provider.label,
            "refsSupported": gi.ref_limit(provider.model) > 0}


# ---------------------------------------------------------------- 后台任务


@dataclass
class Job:
    id: str
    seq: int
    episode: str
    kind: str
    title: str
    steps: list[tuple[str, list[str]]]  # [(显示的命令, 实际运行的参数)]
    status: str = "queued"  # queued running done failed cancelled
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    lines: list[str] = field(default_factory=list)
    dropped: int = 0  # 日志太长时从开头丢掉的行数
    progress_at: dict[str, float] = field(default_factory=dict)  # 每种进度行上次记下的时间
    error: str = ""
    proc: subprocess.Popen | None = None
    cancelled: bool = False


def child_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", NO_COLOR="1", FORCE_COLOR="0")
    return env


def kill_tree(proc: subprocess.Popen) -> None:
    """结束任务的进程和它启动的子进程（uv → python、node → 浏览器）。"""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, check=False)
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)


def error_summary(lines: list[str]) -> str:
    """从日志里找出失败原因：脚本报错时打印的「错误：」那一段，没有就找最后一行提到失败的。"""
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith("错误："):
            block = [lines[i].removeprefix("错误：")]
            for extra in lines[i + 1:]:
                if not extra.startswith((" ", "\t")) or not extra.strip():
                    break
                block.append(extra.strip())
            return "\n".join(block)
    useful = [s.strip() for s in lines if s.strip() and not s.startswith(("$ ", "（退出码"))]
    for line in reversed(useful):
        if "失败" in line or "Error" in line:
            return line
    return useful[-1] if useful else "任务没有成功"


class JobQueue:
    """后台任务一次只运行一个（各个脚本会改同一批文件），其余排队。"""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.jobs: dict[str, Job] = {}
        self.pending: queue.Queue[Job] = queue.Queue()
        self.counter = itertools.count()
        self.env = child_env()
        threading.Thread(target=self._worker, name="jobs", daemon=True).start()

    def _active(self, episode: str) -> Job | None:
        return next((j for j in self.jobs.values() if j.episode == episode and j.status in ("queued", "running")), None)

    def active(self, episode: str) -> Job | None:
        with self.lock:
            return self._active(episode)

    def latest(self, episode: str) -> Job | None:
        with self.lock:
            return max((j for j in self.jobs.values() if j.episode == episode), key=lambda j: j.seq, default=None)

    def get(self, job_id: str) -> Job:
        with self.lock:
            job = self.jobs.get(job_id)
        if job is None:
            raise HttpError(404, "找不到这个任务（网页重启后，之前的任务记录不会保留）")
        return job

    def submit(self, episode: str, kind: str, title: str, steps: list[tuple[str, list[str]]]) -> Job:
        with self.lock:
            if self._active(episode):
                raise HttpError(409, BUSY)
            job = Job(uuid.uuid4().hex[:12], next(self.counter), episode, kind, title, steps)
            self.jobs[job.id] = job
            finished = [j for j in self.jobs.values() if j.status not in ("queued", "running")]
            for old in finished[:-50]:
                del self.jobs[old.id]
        self.pending.put(job)
        return job

    def public(self, job: Job, offset: int | None = None) -> dict:
        with self.lock:
            ahead = 0
            if job.status == "queued":
                ahead = sum(1 for j in self.jobs.values()
                            if j.status == "running" or (j.status == "queued" and j.seq < job.seq))
            data = {"id": job.id, "episode": job.episode, "kind": job.kind, "title": job.title, "status": job.status,
                    "created": job.created, "started": job.started, "finished": job.finished, "error": job.error,
                    "ahead": ahead, "lineCount": job.dropped + len(job.lines)}
            if offset is not None:
                data["lines"] = job.lines[max(0, offset - job.dropped):]
                data["offset"] = job.dropped + len(job.lines)
                data["truncated"] = offset < job.dropped
        return data

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        with self.lock:
            if job.status not in ("queued", "running"):
                return job
            job.cancelled = True
            if job.status == "queued":
                job.status, job.finished = "cancelled", time.time()
            proc = job.proc
        if proc:
            kill_tree(proc)
        self._log(job, "已取消")
        return job

    def shutdown(self) -> None:
        with self.lock:
            procs = [j.proc for j in self.jobs.values() if j.proc]
        for proc in procs:
            kill_tree(proc)

    def _log(self, job: Job, text: str) -> None:
        text = ANSI_RE.sub("", text).rstrip()
        progress = PROGRESS_RE.match(text)
        now = time.monotonic()
        with self.lock:
            if progress and progress.group(2) != progress.group(3):
                if now - job.progress_at.get(progress.group(1), 0.0) < 1:
                    return
                job.progress_at[progress.group(1)] = now
            job.lines.append(text)
            if len(job.lines) > MAX_LOG_LINES:
                cut = len(job.lines) - MAX_LOG_LINES
                del job.lines[:cut]
                job.dropped += cut

    def _worker(self) -> None:
        while True:
            job = self.pending.get()
            with self.lock:
                if job.status != "queued":  # 排队时被取消了
                    continue
                job.status, job.started = "running", time.time()
            try:
                ok = self._run(job)
            except Exception as err:  # 任务线程不能因为意外错误退出，否则后面的任务都不会运行
                self._log(job, f"错误：{type(err).__name__}: {err}")
                ok = False
            with self.lock:
                job.finished = time.time()
                job.proc = None
                if job.cancelled:
                    job.status = "cancelled"
                elif ok:
                    job.status = "done"
                else:
                    job.status = "failed"
                    job.error = error_summary(job.lines)

    def _run(self, job: Job) -> bool:
        for display, argv in job.steps:
            if job.cancelled:
                return False
            self._log(job, f"$ {display}")
            try:
                proc = subprocess.Popen(
                    argv, cwd=ROOT, env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                    **({} if os.name == "nt" else {"start_new_session": True}),
                )
            except OSError as err:
                self._log(job, f"错误：没能启动 {Path(argv[0]).name}：{err}")
                return False
            with self.lock:
                job.proc = proc
            if job.cancelled:
                kill_tree(proc)
            assert proc.stdout is not None
            for line in proc.stdout:  # 进度条用 \r 刷新的行也会按行读出来
                self._log(job, line)
            code = proc.wait()
            if code != 0:
                if not job.cancelled:
                    self._log(job, f"（退出码 {code}）")
                return False
        return True


jobs = JobQueue()


def py(script: str, *args: str) -> tuple[str, list[str]]:
    return f"uv run scripts/{script} {' '.join(args)}".rstrip(), [UV or "uv", "run", f"scripts/{script}", *args]


def clean_options(opts: dict) -> dict:
    """新写分镜时用的音色、语速、画面比例和图片张数：检查格式，没填的用默认值。"""
    voice = str(opts.get("voice") or "zh-CN-YunxiNeural")
    rate = str(opts.get("rate") or "+5%")
    aspect = str(opts.get("aspect") or "9:16")
    if not VOICE_RE.fullmatch(voice):
        raise HttpError(400, "音色的格式不对")
    if not RATE_RE.fullmatch(rate):
        raise HttpError(400, "语速的格式不对，例如 +5%")
    if aspect not in be.SIZES:
        raise HttpError(400, "画面比例不对")
    images = int_option(opts["images"], 1, 500, "图片张数") if opts.get("images") else None
    return {"voice": voice, "rate": rate, "aspect": aspect, "images": images}


def storyboard_options(opts: dict) -> list[str]:
    o = clean_options(opts)
    args = ["--voice", o["voice"], f"--rate={o['rate']}", "--aspect", o["aspect"]]  # --rate=-10% 要连写，否则会被当成参数名
    if o["images"]:
        args += ["--images", str(o["images"])]
    return args


# 网页上最近一次选的新写分镜选项，下次打开这一集时还显示这些
OPTIONS_FILE = "options.json"


def save_options(ep: str, opts: dict) -> None:
    path = episode_dir(ep) / OPTIONS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    be.write_json(path, clean_options(opts))


def saved_options(ep: str) -> dict | None:
    data = gi.read_json(episode_dir(ep) / OPTIONS_FILE)
    if not isinstance(data, dict) or not data:
        return None
    try:
        return clean_options(data)
    except HttpError:  # 手改坏了就当没有
        return None


def start_job(ep: str, body: dict) -> dict:
    check_episode(ep)
    kind = str(body.get("kind") or "")
    opts = body.get("options") or {}
    if not isinstance(opts, dict):
        raise HttpError(400, "任务参数的格式不对")
    settings = effective_settings()
    sb, error = load_storyboard(ep)
    sb_exists = (episode_dir(ep) / "storyboard.json").exists()
    if error and kind not in ("storyboard", "draft"):  # 分镜文件坏了时，只能按文案重写
        raise HttpError(400, error)
    has_script = be.find_script(ep, None) is not None

    def need_llm() -> None:
        if not all(settings.get(k) for k in LLM_KEYS):
            raise HttpError(400, "还没有填写大模型设置，请先到「设置」里填写", "settings")

    def need_script() -> None:
        if not has_script:
            raise HttpError(400, "还没有文案")

    def need_storyboard() -> None:
        if not sb:
            raise HttpError(400, "还没有分镜，先写分镜")

    if kind == "storyboard":
        need_script()
        need_llm()
        steps = [py("gen_storyboard.py", ep, *storyboard_options(opts), *(["--force"] if sb_exists else []))]
        title = "AI 重写分镜" if sb_exists else "AI 写分镜"
    elif kind == "draft":
        need_script()
        steps = [py("build_episode.py", ep, *storyboard_options(opts), *(["--redraft"] if sb_exists else []))]
        title = "按配音时长生成分镜草稿"
    elif kind == "style":
        need_storyboard()
        need_llm()
        steps, title = [py("gen_storyboard.py", ep, "--style")], "AI 推荐画风"
    elif kind == "voice":
        need_storyboard()
        steps, title = [py("build_episode.py", ep)], "更新配音和时间线"
    elif kind == "images":
        _, provider, selection = image_ready(ep, opts)
        args = ["--yes", "--auto-fix", "--provider", provider.key]
        if selection.pilot:
            args += ["--pilot", str(selection.pilot)]
        if selection.force:
            args.append("--force")
        if selection.only:
            args += ["--only", selection.only]
        if opts.get("noRefs"):
            args.append("--no-refs")
        if opts.get("maxCost") is not None:
            args += ["--max-cost", f"{float_option(opts['maxCost'], 0, 10000, '费用上限'):g}"]
        steps = [py("gen_images.py", ep, *args)]
        ids = (selection.only or "").split(",")
        title = {"pilot": f"试画 {selection.pilot} 张", "all": "全部重画", "missing": "生成缺少的图片"}.get(
            selection.mode, f"重画 {'、'.join(ids[:3])}{' 等' if len(ids) > 3 else ''}")
    elif kind in ("render", "make"):
        if not NODE or not REMOTION_CLI.exists():
            raise HttpError(400, "没有找到 Node.js 或项目依赖，请先在项目文件夹里运行 npm install")
        OUT_DIR.mkdir(exist_ok=True)
        if kind == "render":
            need_storyboard()
            if not summary(ep)["imageCount"]["have"]:
                raise HttpError(400, "一张图片都还没有，先出图再导出")
            steps = [py("build_episode.py", ep, "--fill-missing"),
                     (f"npx remotion render ep{ep} out/{ep}.mp4",
                      [NODE, str(REMOTION_CLI), "render", f"ep{ep}", f"out/{ep}.mp4"]),
                     py("make_cover.py", ep)]
            title = "导出视频和封面"
        else:
            args = ["--max-cost", f"{float_option(opts.get('maxCost', 20), 0, 10000, '费用上限'):g}"]
            if sb:
                info = summary(ep)
                if info["draft"]:
                    raise HttpError(400, "分镜还是草稿（没有画面提示词），先让 AI 重写分镜，或者自己填写提示词")
                need_images = info["imageCount"]["have"] < info["imageCount"]["need"]
                if need_images and not info["hasStyle"]:
                    raise HttpError(400, "还没有画风，出图前先在「整体设置」里让 AI 推荐一个，或者自己填写", "style")
            else:
                need_script()
                need_llm()
                need_images = True
                args += storyboard_options(opts)
            if need_images:
                args += ["--provider", choose_provider(settings, str(opts.get("provider") or "")).key]
            if opts.get("noRefs"):
                args.append("--no-refs")
            steps, title = [py("make_video.py", ep, *args)], "一键生成视频"
    else:
        raise HttpError(400, f"不认识的任务：{kind}")
    job = jobs.public(jobs.submit(ep, kind, title, steps))
    if kind in ("storyboard", "draft") or (kind == "make" and not sb):
        save_options(ep, opts)
    return job


# ---------------------------------------------------------------- 接口


@dataclass
class Request:
    query: dict[str, str]
    body: dict


@dataclass
class Binary:
    data: bytes
    content_type: str


ROUTES: list[tuple[str, re.Pattern, Callable]] = []


def route(method: str, pattern: str) -> Callable:
    def register(fn: Callable) -> Callable:
        ROUTES.append((method, re.compile(pattern), fn))
        return fn
    return register


@route("GET", r"/api/settings")
def api_settings(req: Request) -> dict:
    return get_settings()


@route("PUT", r"/api/settings")
def api_save_settings(req: Request) -> dict:
    save_settings(req.body.get("values"))
    return get_settings()


@route("POST", r"/api/settings/test-llm")
def api_test_llm(req: Request) -> dict:
    return test_llm(req.body)


@route("GET", r"/api/voice-sample")
def api_voice_sample(req: Request) -> Binary:
    return Binary(voice_sample(req.query.get("voice", ""), req.query.get("rate", "+0%")), "audio/mpeg")


@route("GET", r"/api/episodes")
def api_episodes(req: Request) -> dict:
    return {"episodes": [summary(ep) for ep in episode_ids()], "ready": readiness(effective_settings())}


CREATE_LOCK = threading.Lock()


@route("POST", r"/api/episodes")
def api_create_episode(req: Request) -> dict:
    opts = req.body.get("options")
    if opts is not None and not isinstance(opts, dict):
        raise HttpError(400, "选项的格式不对")
    if opts:
        clean_options(opts)  # 先检查，格式不对就不新建
    with CREATE_LOCK:
        ep = next_episode_id()
        write_script(ep, req.body, None)
        if opts:
            save_options(ep, opts)
    return summary(ep)


@route("GET", r"/api/episodes/([A-Za-z0-9-]+)")
def api_episode(req: Request, ep: str) -> dict:
    return detail(ep)


@route("PUT", r"/api/episodes/([A-Za-z0-9-]+)/script")
def api_save_script(req: Request, ep: str) -> dict:
    check_episode(ep)
    if jobs.active(ep):
        raise HttpError(409, BUSY)
    write_script(ep, req.body, be.find_script(ep, None))
    return detail(ep)


@route("PUT", r"/api/episodes/([A-Za-z0-9-]+)/storyboard")
def api_save_storyboard(req: Request, ep: str) -> dict:
    """保存网页上改过的分镜，然后在后台更新配音、字幕和时间线（台词没改时几秒就好）。"""
    check_episode(ep)
    path = episode_dir(ep) / "storyboard.json"
    if not path.exists():
        raise HttpError(400, "还没有分镜")
    sb = req.body.get("storyboard")
    validate_storyboard(sb)
    if jobs.active(ep):
        raise HttpError(409, BUSY)
    shutil.copyfile(path, path.with_name("storyboard.bak.json"))
    be.write_json(path, sb)
    return {"job": jobs.public(jobs.submit(ep, "voice", "更新配音和时间线", [py("build_episode.py", ep)]))}


@route("GET", r"/api/episodes/([A-Za-z0-9-]+)/estimate")
def api_estimate(req: Request, ep: str) -> dict:
    return estimate_images(ep, req.query)


@route("POST", r"/api/episodes/([A-Za-z0-9-]+)/jobs")
def api_start_job(req: Request, ep: str) -> dict:
    return start_job(ep, req.body)


@route("GET", r"/api/jobs/([0-9a-f]+)")
def api_job(req: Request, job_id: str) -> dict:
    return jobs.public(jobs.get(job_id), int_option(req.query.get("offset", 0), 0, 10**9, "offset"))


@route("POST", r"/api/jobs/([0-9a-f]+)/cancel")
def api_cancel_job(req: Request, job_id: str) -> dict:
    return jobs.public(jobs.cancel(job_id))


@route("POST", r"/api/episodes/([A-Za-z0-9-]+)/reveal")
def api_reveal(req: Request, ep: str) -> dict:
    """在资源管理器（访达）里打开 out/ 并选中这一集的成片。窗口开在运行后台的这台电脑上。"""
    check_episode(ep)
    reveal(OUT_DIR / f"{ep}.mp4")
    return {"ok": True}


def reveal(path: Path) -> None:
    if not path.is_file():
        raise HttpError(404, "还没有导出视频")
    try:
        if sys.platform == "win32":
            # explorer 要求 /select, 后面紧跟带引号的路径，用列表传参会把整段加上引号导致选不中
            subprocess.Popen(f'explorer /select,"{path}"')
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])
    except OSError as err:
        raise HttpError(500, f"打不开文件夹：{err}") from err


# ---------------------------------------------------------------- HTTP


def safe_file(base: Path, rel: str) -> Path | None:
    """base 文件夹里的文件；不允许跳出 base，也不提供以 . 开头的文件。"""
    parts = [p for p in re.split(r"[\\/]", rel) if p]
    if not parts or any(p.startswith(".") for p in parts):
        return None
    path = base.joinpath(*parts).resolve()
    root = base.resolve()
    return path if root in path.parents and path.is_file() else None


NO_BUILD_PAGE = """<!doctype html><meta charset="utf-8"><title>图文口播视频</title>
<body style="font-family:system-ui,sans-serif;padding:40px;line-height:1.8">
<h2>网页还没有构建</h2><p>请在项目文件夹里运行 <code>npm run web</code>（会先构建网页再启动）。</p></body>"""


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # Windows 上 SO_REUSEADDR 会让两个程序同时占用同一个端口，端口被占用时应该直接报错
    allow_reuse_address = os.name != "nt"
    local_only = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ImageStoryVideo"
    server: Server

    def log_message(self, format: str, *args) -> None:  # 不逐条打印请求
        pass

    def do_GET(self) -> None:
        self.handle_request("GET")

    def do_HEAD(self) -> None:
        self.handle_request("HEAD")

    def do_POST(self) -> None:
        self.handle_request("POST")

    def do_PUT(self) -> None:
        self.handle_request("PUT")

    def send_response(self, code: int, message: str | None = None) -> None:
        self.response_started = True
        super().send_response(code, message)

    def handle_request(self, method: str) -> None:
        self.response_started = False  # 同一个连接会处理多个请求
        url = urlsplit(self.path)
        path = unquote(url.path)
        query = {k: v[-1] for k, v in parse_qs(url.query).items()}
        try:
            body = self.read_json() if method in ("POST", "PUT") else {}
            if not self.host_allowed():
                raise HttpError(403, "只允许通过本机地址（127.0.0.1 或 localhost）或 IP 地址访问")
            if path.startswith("/api/"):
                self.handle_api(method, path, Request(query, body))
            elif method in ("GET", "HEAD"):
                self.handle_static(path, query, method == "HEAD")
            else:
                raise HttpError(405, "不支持这个请求")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True
        except Exception as err:
            if not isinstance(err, HttpError):
                traceback.print_exc()
            if method in ("POST", "PUT") or not isinstance(err, HttpError):
                self.close_connection = True
            if self.response_started:  # 响应已经发出一半，不能再接着写错误信息，断开连接让浏览器重试
                self.close_connection = True
                return
            with contextlib.suppress(OSError):
                if isinstance(err, HttpError):
                    self.send_json({"error": err.message, "code": err.code}, err.status)
                else:
                    self.send_json({"error": "网页后台出错了，详情见运行 npm run web 的终端窗口"}, 500)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 10_000_000:
            raise HttpError(413, "内容太大")
        raw = self.rfile.read(length) if length > 0 else b""
        if not raw:
            return {}
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            raise HttpError(415, "只接受 JSON")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise HttpError(400, "JSON 格式不对") from None
        if not isinstance(data, dict):
            raise HttpError(400, "JSON 格式不对")
        return data

    def host_allowed(self) -> bool:
        """检查 Host，防止别的网站用 DNS 重绑定的办法访问这里：重绑定要用对方的域名，所以只认本机地址，
        监听局域网时再加上 IP 地址和本机的计算机名。"""
        host = (self.headers.get("Host") or "").lower()
        name = host[1:].split("]", 1)[0] if host.startswith("[") else host.rsplit(":", 1)[0]
        if name in LOCAL_HOSTS:
            return True
        if self.server.local_only:
            return False
        try:
            ipaddress.ip_address(name)
            return True
        except ValueError:
            return name in {socket.gethostname().lower(), socket.getfqdn().lower()}

    def same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        return not origin or urlsplit(origin).netloc.lower() == (self.headers.get("Host") or "").lower()

    def handle_api(self, method: str, path: str, req: Request) -> None:
        if method != "GET" and not self.same_origin():
            raise HttpError(403, "拒绝了来自其他网站的请求")
        for route_method, pattern, handler in ROUTES:
            m = pattern.fullmatch(path)
            if m and route_method == method:
                result = handler(req, *m.groups())
                if isinstance(result, Binary):
                    self.send_bytes(result.data, result.content_type, "max-age=3600")
                else:
                    self.send_json(result)
                return
        raise HttpError(404, "没有这个接口")

    def send_bytes(self, data: bytes, content_type: str, cache: str = "no-store", status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_json(self, data, status: int = 200) -> None:
        self.send_bytes(json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8",
                        status=status)

    def handle_static(self, path: str, query: dict[str, str], head: bool) -> None:
        if path in ("/", "/index.html"):
            index = DIST_DIR / "index.html"
            if not index.is_file():
                return self.send_bytes(NO_BUILD_PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return self.send_file(index, head, "no-cache")
        if path.startswith("/out/"):
            file = safe_file(OUT_DIR, path[5:])
        else:
            file = safe_file(DIST_DIR, path) or safe_file(PUBLIC_DIR, path)
        if file is None:
            raise HttpError(404, "找不到这个文件")
        # 带版本号的网址和构建出的文件（文件名里有哈希）内容不会变，其余每次都向服务器确认
        immutable = "v" in query or path.startswith("/assets/")
        self.send_file(file, head, "public, max-age=31536000, immutable" if immutable else "no-cache",
                       query.get("download"))

    def send_file(self, file: Path, head: bool, cache: str, download: str | None = None) -> None:
        st = file.stat()
        etag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
        sent = [t.strip().removeprefix("W/") for t in (self.headers.get("If-None-Match") or "").split(",")]
        if etag in sent or "*" in sent:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        size = st.st_size
        start, end, status = 0, size - 1, 200
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", (self.headers.get("Range") or "").strip())
        if m and size and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
            else:  # bytes=-500：最后 500 个字节
                start = max(0, size - int(m.group(2)))
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", CONTENT_TYPES.get(file.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(end - start + 1 if size else 0))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", etag)
        self.send_header("Last-Modified", formatdate(st.st_mtime, usegmt=True))
        self.send_header("Cache-Control", cache)
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download:
            name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", download).strip() or file.name
            self.send_header("Content-Disposition",
                             f"attachment; filename=\"{quote(file.name)}\"; filename*=UTF-8''{quote(name)}")
        self.end_headers()
        if head or not size:
            return
        # 每次只打开文件读一小段：浏览器慢慢接收时也不会一直占着文件，脚本才能替换它（Windows 上打开着的文件不能被替换）
        pos = start
        with contextlib.suppress(FileNotFoundError, PermissionError):  # 发送途中文件被删掉或正在被替换
            while pos <= end:
                with open(file, "rb") as f:
                    f.seek(pos)
                    chunk = f.read(min(1 << 20, end - pos + 1))
                if not chunk:
                    break
                self.wfile.write(chunk)
                pos += len(chunk)
        if pos <= end:  # 文件中途变短了：没法按 Content-Length 发完，断开连接，浏览器会重新请求
            self.close_connection = True


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="网页版：在浏览器里点一点做视频")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认只允许本机访问")
    parser.add_argument("--port", type=int, default=3100, help="端口，默认 3100")
    parser.add_argument("--no-open", action="store_true", help="启动后不自动打开浏览器")
    args = parser.parse_args()

    if not UV:
        print("注意：没有找到 uv，写分镜、出图等任务都没法运行（winget install astral-sh.uv）")
    if not has_ffmpeg():
        print("注意：没有找到 ffmpeg，配音、出图和导出都没法运行（winget install Gyan.FFmpeg）")
    if not NODE or not REMOTION_CLI.exists():
        print("注意：没有找到 Node.js 或项目依赖，没法导出视频（先在项目文件夹里运行 npm install）")
    if not (DIST_DIR / "index.html").is_file():
        print("注意：网页还没有构建，请用 npm run web 启动（会先构建网页）")
    Server.local_only = args.host in LOCAL_HOSTS
    try:
        server = Server((args.host, args.port), Handler)
    except OSError as err:
        be.die(f"没能在端口 {args.port} 启动网页（{err.strerror or err}），可能被别的程序占用了。"
               f"换一个端口试试：npm run web -- --port {args.port + 1}")
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::', '') else args.host}:{args.port}"
    print(f"网页已启动：{url}（按 Ctrl+C 停止）", flush=True)
    if not Server.local_only:
        print("注意：网页没有登录，能访问这台电脑的人都能打开它、用你的 API Key 花钱")
    if not args.no_open:
        threading.Timer(0.8, webbrowser.open, [url]).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\n正在停止…")
    finally:
        jobs.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
