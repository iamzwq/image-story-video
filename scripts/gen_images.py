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

API Key 等配置写在项目根目录的 .env 里（参考 .env.example）。
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import html
import json
import random
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, replace
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
ALIASES = {
    "bailian": "bailian", "aliyun": "bailian", "dashscope": "bailian", "qwen": "bailian", "z-image": "bailian",
    "ark": "ark", "volc": "ark", "volcengine": "ark", "seedream": "ark", "doubao": "ark", "jimeng": "ark",
}
LABELS = {"bailian": "阿里云百炼", "ark": "火山方舟"}
REWRITE_PROMPT = (
    "下面这条中文出图提示词被生图平台的内容审核拦截了。请改写它：保留画面的主体、场景和时代特征，"
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

    def generate(self, prompt: str, negative: str, size: tuple[int, int]) -> bytes:
        return self._bailian(prompt, negative, size) if self.key == "bailian" else self._ark(prompt, size)

    def _bailian(self, prompt: str, negative: str, size: tuple[int, int]) -> bytes:
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
        payload = {
            "model": self.model,
            "input": {"messages": [{"role": "user", "content": [{"text": prompt[:800]}]}]},
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

    def _ark(self, prompt: str, size: tuple[int, int]) -> bytes:
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "size": f"{size[0]}x{size[1]}",
            "response_format": "url",  # 先拿链接再下载：网络不稳定时可以断点续传，不用重新生成
            "watermark": False,  # 默认会在右下角加「AI 生成」水印
        }
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


def configured_providers() -> dict[str, Provider]:
    found: dict[str, Provider] = {}
    if env("DASHSCOPE_API_KEY"):
        found["bailian"] = Provider(
            "bailian", env("DASHSCOPE_IMAGE_MODEL", "z-image-turbo"), env("DASHSCOPE_API_KEY"),
            env("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com").rstrip("/"),
        )
    if env("ARK_API_KEY"):
        found["ark"] = Provider(
            "ark", env("ARK_IMAGE_MODEL", "doubao-seedream-5-5-261028"), env("ARK_API_KEY"),
            env("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/"),
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


def estimate(model: str) -> float | None:
    """单张图的参考价（元）。模型名里的点和横线视为相同，并按最长前缀匹配，如 doubao-seedream-5-5-261028。"""
    norm = model.replace(".", "-")
    best = max((k for k in PRICES if norm.startswith(k.replace(".", "-"))), key=len, default=None)
    return PRICES[best] if best else None


def compose_prompt(scene: dict, style: str, aspect: str) -> str:
    parts = [scene.get("prompt", "").strip().rstrip("，。,. "), style.strip().rstrip("，。,. "), be.ASPECT_HINT.get(aspect, "")]
    return "，".join(p for p in parts if p)


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


def run_jobs(jobs: list[tuple[Provider, dict, Path]], sb: dict, args: argparse.Namespace) -> tuple[list, list, dict]:
    style = sb.get("imageStyle", be.DEFAULT_STYLE)
    negative = sb.get("negativePrompt", be.DEFAULT_NEGATIVE)
    aspect = sb.get("aspect", "9:16")
    size = GEN_SIZES[aspect]
    llm = llm_settings() if getattr(args, "auto_fix", False) and not args.compare else None
    lock = threading.Lock()
    stopped: dict[str, str] = {}  # 账号、Key 出问题的平台 → 原因；只停这个平台的任务，其他平台照常
    done: list[tuple[Provider, dict, Path]] = []
    failed: list[tuple[Provider, dict, str]] = []
    fixed: dict[str, str] = {}
    total = len(jobs)

    def attempt(provider: Provider, scene_id: str, prompt_text: str, dest_dir: Path) -> Path:
        full_prompt = compose_prompt({"prompt": prompt_text}, style, aspect)
        for i in range(4):
            try:
                return save_image(provider.generate(full_prompt, negative, size), dest_dir, scene_id, args.keep_png)
            except ApiError as err:
                if err.fatal or not err.retry or i == 3 or provider.key in stopped:
                    raise
                time.sleep(2 ** (i + 1) + random.random())
        raise ApiError("重试次数已用完")

    def work(job: tuple[Provider, dict, Path]) -> None:
        provider, sc, dest_dir = job
        if provider.key in stopped:
            return
        tag = f"{provider.model} " if len(args.providers) > 1 else ""
        started = time.time()
        prompt_text = sc.get("prompt", "")
        try:
            try:
                path = attempt(provider, sc["id"], prompt_text, dest_dir)
            except ApiError as err:
                if not (err.moderation and llm):
                    raise
                with lock:
                    print(f"  {tag}{sc['id']} 被内容审核拦下，正在让大模型改写提示词后重试…")
                new_prompt = rewrite_prompt(llm, prompt_text, str(err))
                if not new_prompt:
                    raise
                try:
                    path = attempt(provider, sc["id"], new_prompt, dest_dir)
                except ApiError as err2:
                    if err2.moderation:
                        raise ApiError(f"改写提示词后仍未通过审核：{err2}", moderation=True) from None
                    raise
                with lock:
                    fixed[sc["id"]] = new_prompt
            with lock:
                done.append((provider, sc, path))
                print(f"  [{len(done) + len(failed)}/{total}] {tag}{sc['id']} 完成 · {sc.get('visual', '')}（{time.time() - started:.0f} 秒）")
        except ApiError as err:
            if err.fatal:
                with lock:
                    if provider.key not in stopped:
                        stopped[provider.key] = str(err)
                        if args.compare:
                            print(f"  {LABELS[provider.key]}不可用，这个平台的图先不出了：{err}")
                return
            with lock:
                failed.append((provider, sc, str(err)))
                print(f"  [{len(done) + len(failed)}/{total}] {tag}{sc['id']} 失败：{err}")
        except Exception as err:  # 单张图的意外错误不能让整批任务中断
            with lock:
                failed.append((provider, sc, f"{type(err).__name__}: {err}"))
                print(f"  [{len(done) + len(failed)}/{total}] {tag}{sc['id']} 失败：{type(err).__name__}: {err}")

    with cf.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        list(pool.map(work, jobs))
    if stopped and not args.compare:
        be.die(f"{next(iter(stopped.values()))}\n  已停止，已完成的 {len(done)} 张图片已保存。"
               "处理好后重新运行同一条命令，会接着出剩下的图。")
    return done, failed, fixed


def update_manifest(ep_dir: Path, done: list) -> None:
    path = ep_dir / "images" / "_generated.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    stamp = datetime.now().isoformat(timespec="seconds")
    for provider, sc, file in done:
        data[sc["id"]] = {"file": file.name, "provider": provider.key, "model": provider.model,
                          "prompt": sc.get("prompt", ""), "time": stamp}
    be.write_json(path, dict(sorted(data.items())))


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
    result: dict = {"done": 0, "failed": [], "fixed": [], "cost": 0.0, "spent": 0.0}

    scenes = select_scenes(sb, ep_dir, args.episode, args)
    if not scenes:
        print("没有需要生成的图片（已有图片的分镜会跳过；要重画请用 --only 或 --force）")
        return result
    if args.dry_run:
        style = sb.get("imageStyle", be.DEFAULT_STYLE)
        for sc in scenes:
            print(f"{sc['id']} · {sc.get('visual', '')}\n  {compose_prompt(sc, style, sb.get('aspect', '9:16'))}")
        print(f"共 {len(scenes)} 张（未调用接口）")
        return result

    providers = pick_providers(args)
    args.providers = providers
    batches = []
    for p in providers:
        dest = ep_dir / "compare" / compare_dir_name(p.model) if args.compare else ep_dir / "images"
        todo = scenes
        if args.compare and not (args.only or args.force):
            todo = [sc for sc in scenes if not any((dest / f"{sc['id']}{ext}").exists() for ext in be.IMAGE_EXTS)]
        batches.append((p, dest, todo))
    cost = 0.0
    for p, _, todo in batches:
        if not todo:
            print(f"{p.label}：这几张已经生成过，跳过（要重画请加 --force）")
            continue
        yuan = estimate(p.model)
        n = len(todo)
        cost += (yuan or 0) * n
        note = f"，约 {yuan * n:.2f} 元" if yuan else "，单价未知"
        ids = ", ".join(sc["id"] for sc in todo[:12]) + (" 等" if n > 12 else "")
        print(f"{p.label}：生成 {n} 张（{ids}）{note}")
    if args.compare and not any(todo for _, _, todo in batches):
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

    jobs = []
    for p, dest, todo in batches:
        if args.compare:
            dest.mkdir(parents=True, exist_ok=True)
            be.write_json(dest / "_info.json", {"provider": p.key, "model": p.model})
        jobs += [(p, sc, dest) for sc in todo]
    print(f"开始出图（同时 {args.workers} 个请求）…")
    done, failed, fixed = run_jobs(jobs, sb, args)

    if fixed:
        for sc in sb["scenes"]:
            if sc["id"] in fixed:
                sc["prompt"] = fixed[sc["id"]]
        be.write_json(sb_path, sb)
        print(f"有 {len(fixed)} 个分镜的提示词被大模型改写后才通过审核，新提示词已写回 storyboard.json：{', '.join(sorted(fixed))}")
    failed_ids = sorted({sc["id"] for _, sc, _ in failed})
    spent = sum(estimate(p.model) or 0 for p, _, _ in done)
    result.update(done=len(done), failed=failed_ids, fixed=sorted(fixed), spent=spent)
    print()
    print(f"完成 {len(done)} 张，失败 {len(failed)} 张")
    if args.compare:
        if len(done) < len(jobs):
            print("没出成的图，处理好上面的问题后，重新运行同一条命令即可补上（已经出好的会跳过）")
        page = write_compare_page(ep_dir, sb, args.episode)
        print(f"对比页：{be.rel(page)}（在资源管理器里双击，用浏览器打开）")
        return result
    if failed:
        print("失败的分镜可以修改 storyboard.json 里的提示词后，用 --only 重新生成：")
        print(f"  npm run images -- {args.episode} --only {','.join(failed_ids)}")
    if done:
        update_manifest(ep_dir, done)
        if getattr(args, "rebuild", True):
            print("正在更新时间线…")
            be.build(args.episode, argparse.Namespace(script=None, redraft=False, voice=sb.get("voice", "zh-CN-YunyangNeural"),
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
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]+", args.episode):
        be.die("集数编号只能包含字母、数字和 -（例如 001）")
    result = run(args)
    sys.exit(1 if result["failed"] else 0)


if __name__ == "__main__":
    main()
