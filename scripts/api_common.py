"""调用外部 API 的公共代码：HTTP 请求、错误分类、兼容 OpenAI 协议的大模型对话。"""
from __future__ import annotations

import http.client
import json
import re
import time
import urllib.error
import urllib.request

from envfile import env

MODERATION_HINTS = ("sensitive", "datainspection", "ipinfringement", "risk", "audit")
ACCOUNT_HINTS = ("overdue", "arrearage", "notopen", "unpurchased", "unactivated", "freetieronly", "invalidsubscription")
# 模型名写错或已下线（方舟 InvalidEndpointOrModel.NotFound、百炼 Model not exist、OpenAI 兼容接口 model_not_found）
MODEL_HINTS = ("invalidendpointormodel", "modelnotfound", "model_not_found", "model not exist", "model.notfound")
# 额度用完、达到用量上限：虽然返回 429，但要等额度恢复，马上重试没用（方舟 QuotaExceeded.*、SetLimitExceeded 等）
QUOTA_CODES = ("quotaexceeded", "accountquotaexceeded", "setlimitexceeded", "insufficient_quota")
LLM_VARS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")


class ApiError(Exception):
    def __init__(self, message: str, *, retry: bool = False, fatal: bool = False, moderation: bool = False) -> None:
        super().__init__(message)
        self.retry = retry
        self.fatal = fatal
        self.moderation = moderation


class LLMError(Exception):
    """大模型的回答不可用：被截断、为空或格式不对。"""


def classify_error(status: int, body: str) -> ApiError:
    code, message = "", body.strip()[:300]
    try:
        data = json.loads(body)
        err = data.get("error") if isinstance(data.get("error"), dict) else data
        code = str(err.get("code") or "")
        message = str(err.get("message") or message)
    except (ValueError, AttributeError):
        pass
    detail = f"{code}：{message}" if code else message
    low = (code + message).lower()
    moderation = any(h in low for h in MODERATION_HINTS)
    if code.lower().startswith(QUOTA_CODES) and not re.search(r"queue|排队", low):
        return ApiError(f"额度用完或达到了用量上限，等额度恢复后再试：{detail}", fatal=True)
    if status == 429 or status >= 500:
        return ApiError(f"平台繁忙或限流（HTTP {status}）：{detail}", retry=True)
    if status in (401, 403) and not moderation:
        return ApiError(f"API Key 无效或没有权限（HTTP {status}）：{detail}", fatal=True)
    if any(h in low for h in ACCOUNT_HINTS):
        return ApiError(f"账号或模型不可用（余额不足、套餐过期、模型未开通等）：{detail}", fatal=True)
    if any(h in low for h in MODEL_HINTS):
        return ApiError(f"找不到这个模型（模型名写错或已下线，请检查模型名）：{detail}", fatal=True)
    if moderation:
        return ApiError(f"内容审核未通过：{detail}", moderation=True)
    return ApiError(f"请求被拒绝（HTTP {status}）：{detail}")


def post_json(url: str, payload: dict, api_key: str, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        try:
            body = err.read().decode("utf-8", "replace")
        except OSError:
            body = ""
        raise classify_error(err.code, body) from None
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, ConnectionError, OSError) as err:
        raise ApiError(f"网络错误：{type(err).__name__} {err}", retry=True) from None
    except ValueError as err:
        raise ApiError(f"平台返回的不是 JSON：{err}", retry=True) from None


def download(url: str, attempts: int = 6) -> bytes:
    """下载平台返回的图片（链接 24 小时内有效）。图片已经生成并计费，所以下载中断时只重新下载、从断点接着下，不重新生成。"""
    buf = bytearray()
    last: Exception | None = None
    for i in range(attempts):
        headers = {"User-Agent": "image-story-video"}
        if buf:
            headers["Range"] = f"bytes={len(buf)}-"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
                if buf and r.status != 206:
                    buf.clear()  # 服务器不支持断点续传，从头下载
                expected = r.headers.get("Content-Length")
                got = 0
                while chunk := r.read(256 * 1024):
                    buf += chunk
                    got += len(chunk)
                if expected is None or got >= int(expected):
                    return bytes(buf)
                last = ConnectionError(f"连接中断，这次收到 {got}/{expected} 字节")
        except urllib.error.HTTPError as err:
            if err.code == 416 and buf:
                buf.clear()
            elif err.code != 429 and err.code < 500:
                raise ApiError(f"图片已生成，但下载链接不可用（HTTP {err.code}）") from None
            last = err
        except (urllib.error.URLError, http.client.HTTPException, OSError) as err:
            if isinstance(err, http.client.IncompleteRead):
                buf += err.partial
            last = err
        if i < attempts - 1:
            time.sleep(2 * (i + 1))
    raise ApiError(f"图片已生成，但下载 {attempts} 次都没成功：{type(last).__name__} {last}")


def missing_llm_vars() -> list[str]:
    return [name for name in LLM_VARS if not env(name)]


def chat_endpoint(base_url: str) -> str:
    """LLM_BASE_URL 可以只写到 /v1 这一级，这里补全成对话接口的地址。"""
    url = base_url.strip().rstrip("/")
    return url if url.endswith("/chat/completions") else url + "/chat/completions"


def llm_settings() -> tuple[str, str, str] | None:
    """读取 .env 里的大模型配置；没配置齐时返回 None。"""
    if missing_llm_vars():
        return None
    return chat_endpoint(env("LLM_BASE_URL")), env("LLM_API_KEY"), env("LLM_MODEL")


def chat(settings: tuple[str, str, str], messages: list[dict], timeout: int = 600) -> str:
    """调用兼容 OpenAI 协议的对话接口，返回去掉思考过程后的回答文本。"""
    url, key, model = settings
    for attempt in range(3):
        try:
            data = post_json(url, {"model": model, "messages": messages}, key, timeout=timeout)
            break
        except ApiError as err:
            if err.retry and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            raise
    if isinstance(data.get("error"), dict):
        raise ApiError(f"大模型返回错误：{data['error'].get('message') or data['error']}")
    try:
        choice = data["choices"][0]
        content = choice["message"].get("content")
    except (KeyError, IndexError, TypeError):
        raise LLMError(f"返回格式不对：{json.dumps(data, ensure_ascii=False)[:200]}") from None
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if choice.get("finish_reason") == "length":
        raise LLMError("输出被截断了")
    content = re.sub(r"<think>.*?</think>", "", content or "", flags=re.S).strip()
    if not content:
        raise LLMError("模型没有返回内容")
    return content
