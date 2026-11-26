# /// script
# requires-python = ">=3.10"
# dependencies = ["edge-tts>=7.2"]
# ///
"""按 storyboard.json 调用生图 API 批量出图（阿里云百炼 / 火山引擎方舟）。

    npm run images -- 001                    生成所有还没有图片的分镜
    npm run images -- 001 --pilot            先挑 4 张试画风
    npm run images -- 001 --only S07,S22     只生成（或重画）指定的分镜
    npm run images -- 001 --compare --pilot  两个平台各出几张，生成对比页 compare/index.html
    npm run images -- 001 --compare z-image-turbo,qwen-image-3.0   对比不同模型
    npm run images -- 001 --dry-run          只列出要生成的图和提示词，不调用接口
    npm run images -- 001 --no-refs          不带参考图，角色外貌只用文字描述

分镜里有角色表（cast）时，先给用到的角色各画一张定妆图（images/cast/角色名.jpg）；之后每个分镜都把画面里
角色的定妆图，以及 follow 指向的上一格画面，作为参考图一起传给生图接口，让人物和场景前后连贯。

API Key 等配置写在项目根目录的 .env 里（参考 .env.example）。
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import functools
import html
import json
import random
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_episode as be  # noqa: E402
from api_common import ApiError, LLMError, chat, classify_error, download, llm_settings, post_json  # noqa: E402
from envfile import env, load_env  # noqa: E402

# 生图分辨率：9:16 用 1152×2048，两家都在推荐范围内，Seedream 按 ≤2.61MP 档位计费
GEN_SIZES = {"9:16": (1152, 2048), "16:9": (2048, 1152), "1:1": (1536, 1536), "3:4": (1296, 1728)}
# qwen-image-3.0-pro 输出面积 ≤225 万像素按 1K 档计费（0.25 元），超过按 2K 档（0.5 元），所以把尺寸控制在 1K 档以内
QWEN_PRO_1K_PIXELS = 2_250_000
# 2026-11 官网价格（元/张），只用于运行前的费用预估
PRICES = {
    "doubao-seedream-5-5": 0.13, "doubao-seedream-5-0-pro": 0.30, "doubao-seedream-5-0-flash": 0.12,
    "doubao-seedream-5-0-lite": 0.22, "doubao-seedream-4-5": 0.25, "doubao-seedream-4-0": 0.20,
    "z-image-turbo": 0.10, "qwen-image-2.1-turbo": 0.10, "qwen-image-2.1-pro": 0.25,
    "qwen-image-2.0-pro": 0.50, "qwen-image-2.0": 0.20, "qwen-image-3.0-pro": 0.25, "qwen-image-3.0": 0.18,
}
# 参考图另收的钱：(元/张, 每次请求免费的张数)，只用于费用预估；不在表里的模型参考图不收费
INPUT_PRICES = {"doubao-seedream-5-5": (0.05, 0), "doubao-seedream-5-0-pro": (0.02, 1), "qwen-image-3.0": (0.02, 0)}
# 每次请求最多能带几张参考图；不在表里的模型（如 z-image-turbo）不支持参考图，角色外貌只用文字描述
REF_LIMITS = {
    "doubao-seedream-5-5": 10, "doubao-seedream-5-0-pro": 10, "doubao-seedream-5-0-flash": 10,
    "doubao-seedream-5-0": 14, "doubao-seedream-4-5": 14, "doubao-seedream-4-0": 14,
    "qwen-image-3.0": 3, "qwen-image-2.1": 10, "qwen-image-2.0": 3,
}
MAX_CAST_REFS = 4  # 一个画面最多带几张定妆图，再多的角色只用文字描述外貌
REF_EDGE = 1024  # 参考图上传前缩到长边不超过这么多像素：模型看得清，请求也小
SHEET_SIZE = GEN_SIZES["3:4"]  # 定妆图是竖版全身像，和视频比例无关
ALIASES = {
    "bailian": "bailian", "aliyun": "bailian", "dashscope": "bailian", "qwen": "bailian", "z-image": "bailian",
    "ark": "ark", "volc": "ark", "volcengine": "ark", "seedream": "ark", "doubao": "ark", "jimeng": "ark",
}
LABELS = {"bailian": "阿里云百炼", "ark": "火山方舟"}
REWRITE_PROMPT = (
    "下面这条中文出图提示词被生图平台的内容审核拦截了。请改写它：保留画面的主体、场景和时代特征，"
    "人物的称呼（角色名）原样保留，"
    "去掉或弱化可能被判定为暴力血腥、色情、政治敏感、真实人物肖像、商标版权的描述，换成中性、含蓄的表达。"
    "只输出改写后的提示词本身，40–90 字，不要解释，不要加引号。"
)


def image_kind(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG"):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


@dataclass
class Provider:
    key: str
    model: str
    api_key: str
    base_url: str

    @property
    def label(self) -> str:
        return f"{LABELS[self.key]}（{self.model}）"

    def generate(self, prompt: str, negative: str, size: tuple[int, int], refs: list[str] | None = None) -> bytes:
        """refs 是参考图的 data URI，顺序对应提示词里的图1、图2……"""
        if self.key == "bailian":
            return self._bailian(prompt, negative, size, refs or [])
        return self._ark(prompt, size, refs or [])

    def _bailian(self, prompt: str, negative: str, size: tuple[int, int], refs: list[str]) -> bytes:
        w, h = size
        if self.model.startswith("qwen-image-3.0-pro") and w * h > QWEN_PRO_1K_PIXELS:
            k = (QWEN_PRO_1K_PIXELS / (w * h)) ** 0.5
            w, h = int(w * k) // 16 * 16, int(h * k) // 16 * 16
        params: dict = {
            "size": f"{w}*{h}",
            "prompt_extend": env("DASHSCOPE_PROMPT_EXTEND", "false").lower() in ("1", "true", "yes"),
        }
        # 千问 2.1 系列不支持负面提示词（3.0 系列和更早的 2.0 等支持）
        if self.model.startswith("qwen-image") and not self.model.startswith("qwen-image-2.1") and negative:
            params["negative_prompt"] = negative[:500]
        content = [{"image": r} for r in refs] + [{"text": prompt[:800]}]
        payload = {
            "model": self.model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": params,
        }
        data = post_json(f"{self.base_url}/api/v1/services/aigc/multimodal-generation/generation", payload, self.api_key)
        if data.get("code"):
            raise classify_error(400, json.dumps(data, ensure_ascii=False))
        try:
            content = data["output"]["choices"][0]["message"]["content"]
            url = next(part["image"] for part in content if part.get("image"))
        except (KeyError, IndexError, TypeError, StopIteration):
            raise ApiError(f"返回结果里没有图片：{json.dumps(data, ensure_ascii=False)[:300]}") from None
        return download(url)

    def _ark(self, prompt: str, size: tuple[int, int], refs: list[str]) -> bytes:
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "size": f"{size[0]}x{size[1]}",
            "response_format": "url",  # 先拿链接再下载：网络不稳定时可以断点续传，不用重新生成
            "watermark": False,  # 默认会在右下角加「AI 生成」水印
        }
        if refs:
            payload["image"] = refs if len(refs) > 1 else refs[0]
        if self.model.startswith("doubao-seedream-5"):
            payload["output_format"] = "jpeg"
        data = post_json(f"{self.base_url}/images/generations", payload, self.api_key)
        if isinstance(data.get("error"), dict):
            raise classify_error(400, json.dumps(data, ensure_ascii=False))
        items = data.get("data") or []
        if not items:
            raise ApiError(f"返回结果里没有图片：{json.dumps(data, ensure_ascii=False)[:300]}")
        item = items[0]
        if isinstance(item.get("error"), dict):
            raise classify_error(400, json.dumps(item, ensure_ascii=False))
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        if item.get("url"):
            return download(item["url"])
        raise ApiError("返回结果里没有图片数据")


def configured_providers(get: Callable[..., str] = env) -> dict[str, Provider]:
    """已经填了 Key 的生图平台。get(变量名, 默认值) 读取配置，默认读环境变量（网页版传入它读到的设置）。"""
    found: dict[str, Provider] = {}
    if get("DASHSCOPE_API_KEY"):
        found["bailian"] = Provider(
            "bailian", get("DASHSCOPE_IMAGE_MODEL", "z-image-turbo"), get("DASHSCOPE_API_KEY"),
            get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com").rstrip("/"),
        )
    if get("ARK_API_KEY"):
        found["ark"] = Provider(
            "ark", get("ARK_IMAGE_MODEL", "doubao-seedream-5-5-261028"), get("ARK_API_KEY"),
            get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/"),
        )
    return found


def pick_providers(args: argparse.Namespace) -> list[Provider]:
    found = configured_providers()
    if not found:
        be.die("还没有配置生图 API Key：把项目根目录的 .env.example 复制为 .env，填写 DASHSCOPE_API_KEY 或 ARK_API_KEY")
    if isinstance(args.compare, str):
        models = list(dict.fromkeys(m for m in re.split(r"[,，\s]+", args.compare) if m))
        if len(models) < 2:
            be.die("对比模型至少写两个，用逗号分隔，例如 --compare z-image-turbo,qwen-image-3.0")
        chosen = []
        for model in models:
            key = "ark" if model.startswith("doubao-") else "bailian"
            if key not in found:
                var = "DASHSCOPE_API_KEY" if key == "bailian" else "ARK_API_KEY"
                be.die(f"{model} 是{LABELS[key]}的模型，请先在 .env 里填写 {var}")
            chosen.append(replace(found[key], model=model))
        return chosen
    if args.compare:
        if len(found) < 2:
            be.die("对比两个平台需要都配置 API Key（.env 里的 DASHSCOPE_API_KEY 和 ARK_API_KEY）。\n"
                   "  只有一个平台的话，可以对比它的不同模型，例如 --compare z-image-turbo,qwen-image-3.0")
        return [found["ark"], found["bailian"]]
    name = (args.provider or env("IMAGE_PROVIDER")).strip().lower()
    if name:
        key = ALIASES.get(name)
        if key is None:
            be.die(f"不认识的生图平台 {name!r}，可选：bailian（阿里云百炼）或 ark（火山方舟）")
        if key not in found:
            var = "DASHSCOPE_API_KEY" if key == "bailian" else "ARK_API_KEY"
            be.die(f"{LABELS[key]} 还没有配置 API Key：请在 .env 里填写 {var}")
        return [found[key]]
    if len(found) == 1:
        return list(found.values())
    be.die("两个生图平台都配置了：请在 .env 里设置 IMAGE_PROVIDER=bailian 或 IMAGE_PROVIDER=ark，或运行时加 --provider ark")
    return []


def lookup(table: dict, model: str):
    """按模型名查表：点和横线视为相同，按最长前缀匹配，如 doubao-seedream-5-5-261028 → doubao-seedream-5-5。"""
    norm = model.replace(".", "-")
    best = max((k for k in table if norm.startswith(k.replace(".", "-"))), key=len, default=None)
    return table[best] if best else None


def estimate(model: str) -> float | None:
    """单张图的参考价（元）。"""
    return lookup(PRICES, model)


def ref_cost(model: str, n: int) -> float:
    """一次请求带 n 张参考图要另付的钱（元）。"""
    price, free = lookup(INPUT_PRICES, model) or (0.0, 0)
    return price * max(0, n - free)


def ref_limit(model: str) -> int:
    """这个模型每次请求最多能带几张参考图，0 表示不支持。"""
    return lookup(REF_LIMITS, model) or 0


def ref_intro(names: list[str], follow: bool) -> str:
    """说明每张参考图是什么，放在提示词最前面。names 是带了定妆图的角色，follow 表示最后一张是上一格画面。"""
    parts = []
    if len(names) == 1:
        parts.append(f"图1是{names[0]}的定妆图，画中{names[0]}的相貌、发型、服饰和配色要和定妆图一致")
    elif names:
        labels = "、".join(f"图{i}" for i in range(1, len(names) + 1))
        parts.append(f"{labels}依次是{'、'.join(names)}的定妆图，画中这几个人物的相貌、发型、服饰和配色要和各自的定妆图一致")
    if names:
        parts[-1] += "，动作、神态和位置按画面描述来画，不要照搬定妆图的站姿和纯色背景。"
    if follow:
        parts.append(f"图{len(names) + 1}是上一格画面，沿用它的地点、陈设、光线和色调，"
                     "构图、景别和人物动作按画面描述重新安排，不要照抄。")
    return ("".join(parts) + "画面：") if parts else ""


def compose(sc: dict, text: str, cast: dict[str, str], names: list[str], follow: bool, style: str, aspect: str) -> str:
    """完整的出图提示词。names 是带了定妆图的角色；画面里其他角色的外貌用文字写进提示词。"""
    looks = [(n, cast[n]) for n in dict.fromkeys(sc.get("cast") or []) if n in cast and n not in names]
    return ref_intro(names, follow) + be.scene_prompt(text, looks, style, aspect)


@functools.lru_cache(maxsize=64)
def _encode_ref(path: str, mtime_ns: int) -> str:
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vf",
         f"scale='min(iw,{REF_EDGE})':'min(ih,{REF_EDGE})':force_original_aspect_ratio=decrease",
         "-frames:v", "1", "-q:v", "3", "-f", "image2pipe", "-c:v", "mjpeg", "-"],
        capture_output=True, check=False,
    )
    if result.returncode == 0 and result.stdout.startswith(b"\xff\xd8"):
        data, kind = result.stdout, "jpeg"
    else:  # 缩图失败就传原图
        data = Path(path).read_bytes()
        kind = image_kind(data) or "jpeg"
    return f"data:image/{kind};base64,{base64.b64encode(data).decode('ascii')}"


def ref_uri(path: Path) -> str:
    """参考图缩小后编码成接口要的 data URI；同一张图（没改过）只编码一次。"""
    return _encode_ref(str(path), path.stat().st_mtime_ns)


def save_image(data: bytes, dest_dir: Path, scene_id: str, keep_png: bool) -> Path:
    kind = image_kind(data)
    if kind is None:
        raise ApiError("平台返回的数据不是图片")
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest_dir / f".{scene_id}.{threading.get_ident()}.tmp"
    if kind == "png" and not keep_png:
        src = tmp.with_suffix(".png")
        src.write_bytes(data)
        out_tmp = tmp.with_suffix(".jpg")
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-q:v", "2", "-f", "image2", str(out_tmp)],
            capture_output=True, text=True,
        )
        src.unlink(missing_ok=True)
        if result.returncode != 0:
            out_tmp.unlink(missing_ok=True)
            raise ApiError(f"PNG 转 JPEG 失败：{result.stderr.strip()[:200]}")
        final = dest_dir / f"{scene_id}.jpg"
    else:
        out_tmp = tmp.with_suffix(".bin")
        out_tmp.write_bytes(data)
        final = dest_dir / f"{scene_id}.{'jpg' if kind == 'jpeg' else kind}"
    for ext in be.IMAGE_EXTS:
        for old in (dest_dir / f"{scene_id}{ext}", dest_dir / f"{scene_id}{ext.upper()}"):
            if old != final and old.exists():
                old.unlink()
    out_tmp.replace(final)
    return final


def compare_dir_name(model: str) -> str:
    return re.sub(r"[^\w.-]", "_", model)


def write_compare_page(ep_dir: Path, sb: dict, episode: str) -> Path:
    cmp_dir = ep_dir / "compare"
    columns = []
    for folder in sorted(p for p in cmp_dir.iterdir() if (p / "_info.json").is_file()):
        columns.append((folder.name, json.loads((folder / "_info.json").read_text(encoding="utf-8"))))
    rows = []
    empty = "<td class=empty>—</td>"
    for name, look in (sb.get("cast") or {}).items():
        cells = []
        for col, _ in columns:
            img = be.find_cast_image(cmp_dir / col / be.CAST_DIR, name)
            cells.append(f'<td><img src="{html.escape(col)}/{be.CAST_DIR}/{html.escape(img.name)}" loading="lazy"></td>'
                         if img else empty)
        if any(c != empty for c in cells):
            rows.append(f"<tr><th>定妆图<br><span>{html.escape(name)}</span><p>{html.escape(look)}</p></th>{''.join(cells)}</tr>")
    for sc in sb["scenes"]:
        cells = []
        for name, _ in columns:
            img = next((f for ext in be.IMAGE_EXTS for f in [cmp_dir / name / f"{sc['id']}{ext}"] if f.exists()), None)
            cells.append(f'<td><img src="{html.escape(name)}/{html.escape(img.name)}" loading="lazy"></td>' if img
                         else "<td class=empty>—</td>")
        if all(c == "<td class=empty>—</td>" for c in cells):
            continue
        rows.append(
            f"<tr><th>{html.escape(sc['id'])}<br><span>{html.escape(sc.get('visual', ''))}</span>"
            f"<p>{html.escape(sc.get('prompt', ''))}</p></th>{''.join(cells)}</tr>"
        )
    heads = "".join(
        f"<th>{html.escape(LABELS.get(info.get('provider', ''), ''))}<br><span>{html.escape(info.get('model', name))}</span></th>"
        for name, info in columns
    )
    page = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>出图对比 · {html.escape(sb.get('title', episode))}</title>
<style>
body{{font-family:"Microsoft YaHei",sans-serif;background:#16130f;color:#eee;margin:24px}}
table{{border-collapse:collapse}} th,td{{padding:10px;vertical-align:top;text-align:left;border-bottom:1px solid #333}}
th span{{color:#d9b26f;font-weight:normal}} th p{{width:220px;color:#999;font-size:12px;font-weight:normal;line-height:1.5}}
img{{width:300px;border-radius:6px;display:block}} td.empty{{color:#666;text-align:center;width:300px}}
</style></head><body>
<h2>{html.escape(sb.get('title', ''))} · 出图对比</h2>
<p>同一条提示词在不同平台、模型下的效果。选好后在 .env 里设置 IMAGE_PROVIDER 和模型（DASHSCOPE_IMAGE_MODEL 或 ARK_IMAGE_MODEL），再运行 npm run images -- {episode}。</p>
<table><tr><th>分镜</th>{heads}</tr>
{chr(10).join(rows)}
</table></body></html>
"""
    out = cmp_dir / "index.html"
    out.write_text(page, encoding="utf-8")
    return out


def select_scenes(sb: dict, ep_dir: Path, episode: str, args: argparse.Namespace) -> list[dict]:
    image_scenes = [sc for sc in sb["scenes"] if sc.get("type") != "chapter"]
    by_id = {sc["id"]: sc for sc in image_scenes}
    if args.only:
        ids = [x.strip() for x in re.split(r"[,，\s]+", args.only) if x.strip()]
        unknown = [x for x in ids if x not in by_id]
        if unknown:
            be.die(f"找不到这些分镜：{', '.join(unknown)}")
        chosen = [by_id[x] for x in ids]
        for sc in [sc for sc in chosen if sc.get("reuse")]:
            print(f"注意：{sc['id']} 复用 {sc['reuse']} 的图片，不需要单独出图，已跳过")
        chosen = [sc for sc in chosen if not sc.get("reuse")]
    else:
        chosen = [sc for sc in image_scenes if not sc.get("reuse")]
    missing_prompt = [sc["id"] for sc in chosen if not (sc.get("prompt") or "").strip()]
    if missing_prompt:
        print(f"注意：{len(missing_prompt)} 个分镜没有提示词，已跳过（{', '.join(missing_prompt[:8])}{' 等' if len(missing_prompt) > 8 else ''}）")
    chosen = [sc for sc in chosen if (sc.get("prompt") or "").strip()]
    if args.pilot and not args.only and chosen:
        n = min(args.pilot, len(chosen))
        idx = sorted({round(i * (len(chosen) - 1) / max(n - 1, 1)) for i in range(n)})
        chosen = [chosen[i] for i in idx]
    if not (args.only or args.force or args.compare):
        chosen = [sc for sc in chosen if not be.find_image(ep_dir, episode, sc["id"])]
    return chosen


def rewrite_prompt(llm: tuple[str, str, str], prompt: str, reason: str) -> str | None:
    """让大模型改写被内容审核拦下的提示词；失败时返回 None。"""
    try:
        text = chat(llm, [{"role": "system", "content": REWRITE_PROMPT},
                          {"role": "user", "content": f"原提示词：{prompt}\n拦截原因：{reason[:200]}"}], timeout=300)
    except (ApiError, LLMError):
        return None
    text = re.sub(r"\s+", "", text).strip("“”\"'「」『』")
    text = re.sub(r"^(?:改写后的?)?提示词[:：]", "", text)
    return text[:300] or None


@dataclass
class Job:
    provider: Provider
    scene: dict  # 分镜；定妆图任务是 {"id": 角色名}
    dest: Path  # 图片存到哪个文件夹
    sheet: str = ""  # 定妆图任务：角色名
    after: str = ""  # 上一格也在这次生成时，要等它画完：上一格的分镜编号
    refs: list[str] = field(default_factory=list)  # 实际带的参考图：角色名、上一格的分镜编号


@dataclass
class Outcome:
    done: list = field(default_factory=list)  # [(Job, 图片路径)]
    failed: list = field(default_factory=list)  # [(Job, 原因)]
    fixed: dict = field(default_factory=dict)  # 分镜编号 → 改写后才通过审核的提示词
    stopped: dict = field(default_factory=dict)  # 账号、Key 出问题的平台 → 原因


def plan_refs(sc: dict, cast: dict[str, str], limit: int, has_sheet: Callable[[str], bool],
              follow: str | None) -> tuple[list[str], str | None]:
    """这个画面带哪些参考图：(用定妆图的角色名, 上一格的分镜编号)。角色优先，名额不够时不带上一格。
    has_sheet(角色名) 判断定妆图在不在；follow 是能用的上一格，没有图时为 None。"""
    names = [n for n in dict.fromkeys(sc.get("cast") or []) if n in cast][:min(limit, MAX_CAST_REFS)]
    names = [n for n in names if has_sheet(n)]
    return names, (follow if follow and len(names) < limit else None)


def planned_refs(sc: dict, cast: dict[str, str], limit: int, by_id: dict, dest: Path,
                 in_run: set[str]) -> tuple[list[str], str | None]:
    """预估费用、预览时用：假定要用的定妆图都能画好；上一格已经有图，或者这次也会画。"""
    src = be.follow_source(by_id, sc)
    ok = src if src and (src in in_run or be.image_file(dest, src)) else None
    return plan_refs(sc, cast, limit, lambda _: True, ok)


def plan_cost(model: str, todo: list[dict], sheets: list[str], cast: dict[str, str], limit: int, by_id: dict,
              dest: Path) -> tuple[float, list[int]]:
    """预估这一批图的费用（元，单价未知的按 0 算），以及每张分镜带几张参考图。"""
    in_run = {sc["id"] for sc in todo}
    counts = [len(names) + bool(follow) for names, follow in
              (planned_refs(sc, cast, limit, by_id, dest, in_run) for sc in todo)]
    total = (estimate(model) or 0) * (len(todo) + len(sheets)) + sum(ref_cost(model, k) for k in counts)
    return total, counts


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        return {}


def sheets_to_draw(scenes: list[dict], cast: dict[str, str], sheet_dir: Path, style: str, limit: int) -> list[str]:
    """这些分镜要用、但还没有定妆图，或者外貌设定、画风改过的角色。自己放进去的图（没有生成记录）不会重画。"""
    if not limit:
        return []
    made = read_json(sheet_dir / "_generated.json")
    used = dict.fromkeys(n for sc in scenes for n in plan_refs(sc, cast, limit, lambda _: True, None)[0])
    return [n for n in used if be.find_cast_image(sheet_dir, n) is None
            or (n in made and (made[n].get("look") != cast[n] or made[n].get("style") != style))]


def order_jobs(jobs: list[Job], sb: dict, no_refs: bool = False) -> list[Job]:
    """上一格也在这次生成的画面，要等上一格画完才能拿它当参考图。按依赖的层数排队：先画不依赖别的图的，
    再画依赖它们的。线程池按队列顺序取任务，要等的那张一定已经开始画或者画完了，不会互相卡死。"""
    index = {sc["id"]: i for i, sc in enumerate(sb["scenes"])}
    by_id = {sc["id"]: sc for sc in sb["scenes"]}
    depth: dict[tuple[str, str], int] = {}
    for job in sorted(jobs, key=lambda j: index[j.scene["id"]]):  # follow 只会指向前面的画面
        uses_refs = not no_refs and ref_limit(job.provider.model) > 0
        src = (be.follow_source(by_id, job.scene) or "") if uses_refs else ""
        job.after = src if (str(job.dest), src) in depth else ""
        depth[(str(job.dest), job.scene["id"])] = depth[(str(job.dest), src)] + 1 if job.after else 0
    return sorted(jobs, key=lambda j: (depth[(str(j.dest), j.scene["id"])], index[j.scene["id"]]))


def run_jobs(sheet_jobs: list[Job], scene_jobs: list[Job], sb: dict, args: argparse.Namespace) -> Outcome:
    """先画定妆图，再画分镜。"""
    style = sb.get("imageStyle") or ""
    negative = sb.get("negativePrompt", be.DEFAULT_NEGATIVE)
    aspect = sb.get("aspect", "9:16")
    size = GEN_SIZES[aspect]
    cast = sb.get("cast") or {}
    by_id = {sc["id"]: sc for sc in sb["scenes"]}
    no_refs = getattr(args, "no_refs", False)
    llm = llm_settings() if getattr(args, "auto_fix", False) and not args.compare else None
    lock = threading.Lock()
    out = Outcome()
    stopped = out.stopped  # 只停出问题的平台，其他平台照常
    finished = {(str(j.dest), j.scene["id"]): threading.Event() for j in scene_jobs}
    progress = [0, 0]  # 这一轮已经结束的张数、这一轮的总张数

    def call(provider: Provider, prompt: str, dims: tuple[int, int], refs: list[str]) -> bytes:
        for i in range(4):
            try:
                return provider.generate(prompt, negative, dims, refs)
            except ApiError as err:
                if err.fatal or not err.retry or i == 3 or provider.key in stopped:
                    raise
                time.sleep(2 ** (i + 1) + random.random())
        raise ApiError("重试次数已用完")

    def draw_sheet(job: Job) -> Path:
        prompt = be.cast_sheet_prompt(job.sheet, cast[job.sheet], style)
        return save_image(call(job.provider, prompt, SHEET_SIZE, []), job.dest, be.cast_filename(job.sheet), args.keep_png)

    def draw_scene(job: Job, tag: str) -> Path:
        sc = job.scene
        limit = 0 if no_refs else ref_limit(job.provider.model)
        sheet_dir = job.dest / be.CAST_DIR
        src = be.follow_source(by_id, sc)
        follow_file = be.image_file(job.dest, src) if src and limit else None
        names, follow = plan_refs(sc, cast, limit, lambda n: be.find_cast_image(sheet_dir, n) is not None,
                                  src if follow_file else None)
        uris = [ref_uri(be.find_cast_image(sheet_dir, n)) for n in names] + ([ref_uri(follow_file)] if follow else [])
        job.refs = names + ([follow] if follow else [])

        def attempt(text: str) -> Path:
            full = compose(sc, text, cast, names, bool(follow), style, aspect)
            return save_image(call(job.provider, full, size, uris), job.dest, sc["id"], args.keep_png)

        prompt_text = sc.get("prompt", "")
        try:
            return attempt(prompt_text)
        except ApiError as err:
            if not (err.moderation and llm):
                raise
            with lock:
                print(f"  {tag}{sc['id']} 被内容审核拦下，正在让大模型改写提示词后重试…")
            new_prompt = rewrite_prompt(llm, prompt_text, str(err))
            if not new_prompt:
                raise
            try:
                path = attempt(new_prompt)
            except ApiError as err2:
                if err2.moderation:
                    raise ApiError(f"改写提示词后仍未通过审核：{err2}", moderation=True) from None
                raise
            with lock:
                out.fixed[sc["id"]] = new_prompt
            return path

    def report(text: str) -> None:  # 调用时要持有 lock
        progress[0] += 1
        print(f"  [{progress[0]}/{progress[1]}] {text}")

    def work(job: Job) -> None:
        key = (str(job.dest), job.scene["id"])
        try:
            if job.after:
                finished[(str(job.dest), job.after)].wait()
            if job.provider.key in stopped:
                return
            tag = f"{job.provider.model} " if len(args.providers) > 1 else ""
            name = f"{tag}定妆图 {job.sheet}" if job.sheet else f"{tag}{job.scene['id']}"
            started = time.time()
            try:
                path = draw_sheet(job) if job.sheet else draw_scene(job, tag)
            except ApiError as err:
                if err.fatal:
                    with lock:
                        if job.provider.key not in stopped:
                            stopped[job.provider.key] = str(err)
                            if args.compare:
                                print(f"  {LABELS[job.provider.key]}不可用，这个平台的图先不出了：{err}")
                    return
                with lock:
                    out.failed.append((job, str(err)))
                    report(f"{name} 失败：{err}")
                return
            except Exception as err:  # 单张图的意外错误不能让整批任务中断
                with lock:
                    out.failed.append((job, f"{type(err).__name__}: {err}"))
                    report(f"{name} 失败：{type(err).__name__}: {err}")
                return
            with lock:
                out.done.append((job, path))
                visual = "" if job.sheet else f" · {job.scene.get('visual', '')}"
                refs = f" · 参考 {'、'.join(job.refs)}" if job.refs else ""
                report(f"{name} 完成{visual}{refs}（{time.time() - started:.0f} 秒）")
        finally:
            if not job.sheet and key in finished:
                finished[key].set()

    for jobs, title in ((sheet_jobs, "先画角色定妆图"), (scene_jobs, "开始出图")):
        if not jobs or (stopped and not args.compare):
            continue
        print(f"{title}（{len(jobs)} 张，同时 {args.workers} 个请求）…")
        progress[:] = [0, len(jobs)]
        with cf.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            list(pool.map(work, jobs))
        lost = sorted({j.sheet for j, _ in out.failed if j.sheet}) if jobs is sheet_jobs else []
        if lost:
            print(f"  这些角色的定妆图没画成，这次用到他们的画面只用文字描述外貌：{'、'.join(lost)}")
    return out


def update_manifest(ep_dir: Path, done: list) -> None:
    path = ep_dir / "images" / "_generated.json"
    data = read_json(path)
    stamp = datetime.now().isoformat(timespec="seconds")
    for job, file in done:
        entry = {"file": file.name, "provider": job.provider.key, "model": job.provider.model,
                 "prompt": job.scene.get("prompt", ""), "time": stamp}
        if job.refs:
            entry["refs"] = job.refs
        data[job.scene["id"]] = entry
    be.write_json(path, dict(sorted(data.items())))


def update_sheet_manifest(done: list, cast: dict[str, str], style: str) -> None:
    """记下每张定妆图是按什么外貌设定、画风画的；之后改了设定或画风会自动重画。"""
    stamp = datetime.now().isoformat(timespec="seconds")
    for folder in {job.dest for job, _ in done}:
        path = folder / "_generated.json"
        data = read_json(path)
        for job, file in done:
            if job.dest == folder:
                data[job.sheet] = {"file": file.name, "provider": job.provider.key, "model": job.provider.model,
                                   "look": cast[job.sheet], "style": style, "time": stamp}
        be.write_json(path, data)


def dry_run_provider(args: argparse.Namespace) -> Provider | None:
    """--dry-run 不要求配好 Key：能确定用哪个平台就按它显示参考图，确定不了返回 None。"""
    found = configured_providers()
    name = (args.provider or env("IMAGE_PROVIDER")).strip().lower()
    key = ALIASES.get(name) if name else (next(iter(found)) if len(found) == 1 else None)
    return found.get(key) if key else None


def show_dry_run(sb: dict, scenes: list[dict], ep_dir: Path, args: argparse.Namespace) -> None:
    style = sb.get("imageStyle") or ""
    aspect = sb.get("aspect", "9:16")
    cast = sb.get("cast") or {}
    by_id = {sc["id"]: sc for sc in sb["scenes"]}
    dest = ep_dir / "images"
    no_refs = getattr(args, "no_refs", False)
    provider = None if no_refs else dry_run_provider(args)
    limit = ref_limit(provider.model) if provider else 0
    if not style.strip():
        print(f"注意：还没有画风（imageStyle 是空的），真正出图前要补上：npm run storyboard -- {args.episode} --style")
    if any(sc.get("cast") or sc.get("follow") for sc in scenes):
        if limit:
            print(f"按 {provider.label} 显示参考图（每次最多 {limit} 张）")
        else:
            reason = "--no-refs" if no_refs else (f"{provider.label}不支持参考图" if provider else "没确定用哪个生图平台")
            print(f"{reason}：不带参考图，角色外貌写进提示词")
    sheets = sheets_to_draw(scenes, cast, dest / be.CAST_DIR, style, limit)
    for n in sheets:
        print(f"定妆图 · {n}\n  {be.cast_sheet_prompt(n, cast[n], style)}")
    in_run = {sc["id"] for sc in scenes}
    for sc in scenes:
        names, follow = planned_refs(sc, cast, limit, by_id, dest, in_run)
        refs = [f"{n}（定妆图）" for n in names] + ([f"{follow}（上一格）"] if follow else [])
        print(f"{sc['id']} · {sc.get('visual', '')}" + (f"\n  参考图：{'、'.join(refs)}" if refs else ""))
        print(f"  {compose(sc, sc.get('prompt', ''), cast, names, bool(follow), style, aspect)}")
    print(f"共 {len(scenes)} 张" + (f"，另有 {len(sheets)} 张定妆图" if sheets else "") + "（未调用接口）")


def run(args: argparse.Namespace) -> dict:
    """出图主流程，返回结果汇总。一键生成（make_video.py）也调用这里。"""
    load_env(be.ROOT)
    if args.compare and not args.only and not args.pilot:
        args.pilot = 4
    ep_dir = be.EPISODES_DIR / args.episode
    sb_path = ep_dir / "storyboard.json"
    if not sb_path.exists():
        be.die(f"还没有 {be.rel(sb_path)}：请先运行 npm run storyboard -- {args.episode} 或 npm run voice -- {args.episode}")
    sb = be.load_storyboard(sb_path)
    be.validate(sb)
    result: dict = {"done": 0, "failed": [], "fixed": [], "cost": 0.0, "spent": 0.0, "sheets": 0}
    cast = sb.get("cast") or {}
    style = sb.get("imageStyle") or ""
    no_refs = getattr(args, "no_refs", False)

    scenes = select_scenes(sb, ep_dir, args.episode, args)
    if not scenes:
        print("没有需要生成的图片（已有图片的分镜会跳过；要重画请用 --only 或 --force）")
        return result
    if args.dry_run:
        show_dry_run(sb, scenes, ep_dir, args)
        return result
    if not style.strip():
        be.die(f"还没有画风：storyboard.json 里的 imageStyle 是空的，各张图会画得五花八门。"
               f"运行 npm run storyboard -- {args.episode} --style 让大模型按内容推荐一个，或者自己填写（可以参考 README 的「画风参考」）")

    providers = pick_providers(args)
    args.providers = providers
    by_id = {sc["id"]: sc for sc in sb["scenes"]}
    batches = []
    for p in providers:
        dest = ep_dir / "compare" / compare_dir_name(p.model) if args.compare else ep_dir / "images"
        todo = scenes
        if args.compare and not (args.only or args.force):
            todo = [sc for sc in scenes if not any((dest / f"{sc['id']}{ext}").exists() for ext in be.IMAGE_EXTS)]
        limit = 0 if no_refs else ref_limit(p.model)
        batches.append((p, dest, todo, sheets_to_draw(todo, cast, dest / be.CAST_DIR, style, limit), limit))
    cost = 0.0
    for p, dest, todo, sheets, limit in batches:
        if not todo:
            print(f"{p.label}：这几张已经生成过，跳过（要重画请加 --force）")
            continue
        yuan = estimate(p.model)
        n = len(todo)
        total, counts = plan_cost(p.model, todo, sheets, cast, limit, by_id, dest)
        cost += total
        note = f"，约 {total:.2f} 元" if yuan else "，单价未知"
        ids = ", ".join(sc["id"] for sc in todo[:12]) + (" 等" if n > 12 else "")
        extra = f"，先画 {len(sheets)} 张角色定妆图（{'、'.join(sheets)}）" if sheets else ""
        refs = f"，共带 {sum(counts)} 张参考图" if sum(counts) else ""
        print(f"{p.label}：生成 {n} 张（{ids}）{extra}{refs}{note}")
        if not limit and not no_refs and any(sc.get("cast") for sc in todo):
            print(f"  {p.model} 不支持参考图，角色只用文字描述外貌，前后一致性会差一些"
                  "（Seedream、qwen-image-3.0 等模型支持参考图）")
    if args.compare and not any(todo for _, _, todo, _, _ in batches):
        page = write_compare_page(ep_dir, sb, args.episode)
        print(f"对比页：{be.rel(page)}（在资源管理器里双击，用浏览器打开）")
        return result
    if cost:
        print(f"预计共约 {cost:.2f} 元（参考价，以平台账单为准；审核未通过或失败的不收费）")
    result["cost"] = cost
    if args.max_cost is not None and cost > args.max_cost:
        be.die(f"预计费用约 {cost:.2f} 元，超过了上限 {args.max_cost:g} 元，已停止，没有产生费用。"
               f"确认没问题的话，用 --max-cost 调高上限后重新运行")
    if not args.yes:
        if not sys.stdin.isatty():
            be.die("需要确认费用：请在终端里直接运行，或加 --yes 跳过确认")
        try:
            answer = input("继续？输入 y 确认：")
        except (EOFError, KeyboardInterrupt):
            print()
            be.die("没有收到确认，已取消（在终端里运行时输入 y 确认，或加 --yes 跳过确认）")
        if answer.strip().lower() not in ("y", "yes"):
            print("已取消")
            return result
    if args.auto_fix and not args.compare and llm_settings() is None:
        print("提示：没有配置大模型（.env 里的 LLM_*），被内容审核拦下的图不会自动改写提示词")

    sheet_jobs: list[Job] = []
    scene_jobs: list[Job] = []
    for p, dest, todo, sheets, _ in batches:
        if args.compare:
            dest.mkdir(parents=True, exist_ok=True)
            be.write_json(dest / "_info.json", {"provider": p.key, "model": p.model})
        sheet_jobs += [Job(p, {"id": n}, dest / be.CAST_DIR, sheet=n) for n in sheets]
        scene_jobs += [Job(p, sc, dest) for sc in todo]
    out = run_jobs(sheet_jobs, order_jobs(scene_jobs, sb, no_refs), sb, args)

    done = [(job, path) for job, path in out.done if not job.sheet]
    failed = [(job, reason) for job, reason in out.failed if not job.sheet]
    if out.fixed:
        for sc in sb["scenes"]:
            if sc["id"] in out.fixed:
                sc["prompt"] = out.fixed[sc["id"]]
        be.write_json(sb_path, sb)
        print(f"有 {len(out.fixed)} 个分镜的提示词被大模型改写后才通过审核，新提示词已写回 storyboard.json："
              f"{', '.join(sorted(out.fixed))}")
    update_sheet_manifest([(job, path) for job, path in out.done if job.sheet], cast, style)
    if done and not args.compare:
        update_manifest(ep_dir, done)
    if out.stopped and not args.compare:
        be.die(f"{next(iter(out.stopped.values()))}\n  已停止，已完成的 {len(out.done)} 张图片已保存。"
               "处理好后重新运行同一条命令，会接着出剩下的图。")
    failed_ids = sorted({job.scene["id"] for job, _ in failed})
    spent = sum((estimate(job.provider.model) or 0) + ref_cost(job.provider.model, len(job.refs)) for job, _ in out.done)
    result.update(done=len(done), failed=failed_ids, fixed=sorted(out.fixed), spent=spent, sheets=len(out.done) - len(done))
    print()
    print(f"完成 {len(done)} 张，失败 {len(failed)} 张" + (f"（另画了 {result['sheets']} 张角色定妆图）" if result["sheets"] else ""))
    if args.compare:
        if len(done) < len(scene_jobs):
            print("没出成的图，处理好上面的问题后，重新运行同一条命令即可补上（已经出好的会跳过）")
        page = write_compare_page(ep_dir, sb, args.episode)
        print(f"对比页：{be.rel(page)}（在资源管理器里双击，用浏览器打开）")
        return result
    if failed:
        print("失败的分镜可以修改 storyboard.json 里的提示词后，用 --only 重新生成：")
        print(f"  npm run images -- {args.episode} --only {','.join(failed_ids)}")
        if any(job.refs for job, _ in failed):
            print("  如果报错和参考图有关，可以加 --no-refs，改成只用文字描述人物")
    if done and getattr(args, "rebuild", True):
        print("正在更新时间线…")
        be.build(args.episode, argparse.Namespace(script=None, redraft=False, voice=sb.get("voice", "zh-CN-YunxiNeural"),
                                                  rate=sb.get("rate", "+0%"), aspect=sb.get("aspect", "9:16")), verbose=False)
        print("下一步：npm run dev 预览（刷新浏览器即可看到新图片）")
    return result


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="按 storyboard.json 调用生图 API 批量出图")
    parser.add_argument("episode", help="集数编号，例如 001")
    parser.add_argument("--provider", help="生图平台：bailian（阿里云百炼）或 ark（火山方舟），默认读 .env 的 IMAGE_PROVIDER")
    parser.add_argument("--only", help="只生成这些分镜，逗号分隔，如 S07,S22（已有图片也会重画）")
    parser.add_argument("--pilot", nargs="?", type=int, const=4, default=0, help="试画风：均匀挑几个分镜出图（默认 4 张）")
    parser.add_argument("--force", action="store_true", help="已有图片也重新生成")
    parser.add_argument("--compare", nargs="?", const=True, default=False, metavar="模型1,模型2",
                        help="不写模型名时两个平台都出图；写模型名（逗号分隔）时对比这些模型。保存到 compare 文件夹并生成对比页")
    parser.add_argument("--yes", "-y", action="store_true", help="跳过费用确认")
    parser.add_argument("--dry-run", action="store_true", help="只列出要生成的图和提示词，不调用接口")
    parser.add_argument("--auto-fix", action="store_true", help="被内容审核拦下时，让大模型改写提示词后自动重试一次")
    parser.add_argument("--max-cost", type=float, help="费用上限（元），预计费用超过时直接停止")
    parser.add_argument("--workers", type=int, default=2, help="同时请求的数量（默认 2）")
    parser.add_argument("--keep-png", action="store_true", help="保留 PNG 原图（默认转成 JPEG 以减小体积）")
    parser.add_argument("--no-refs", action="store_true",
                        help="不带参考图（角色定妆图、上一格画面），角色外貌只用文字描述；Seedream 5.5 每张参考图另收 0.05 元")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]+", args.episode):
        be.die("集数编号只能包含字母、数字和 -（例如 001）")
    result = run(args)
    sys.exit(1 if result["failed"] else 0)


if __name__ == "__main__":
    main()
