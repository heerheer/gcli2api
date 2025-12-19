# openai_transfer.py

import json
from typing import Any, Dict, List
from openai.types.responses import ResponseCreateParams
from src.utils import (
    DEFAULT_SAFETY_SETTINGS,
    get_base_model_name,
    get_thinking_budget,
    should_include_thoughts,
    is_search_model,
)
from log import log

from .openai_transfer import (
    convert_openai_tools_to_gemini,
    convert_tool_choice_to_tool_config,
)


def effort_to_budget(level: str) -> int:
    """
    映射思考level(gpt-5风格)到gemini的thinkingBudget数值
    Convert thinking level string to integer value
    """
    if(level is None):
        return -1
    mapping = {
        "low": 128,
        "medium": 2048,
        "high": 32768,
    }
    try:
        return mapping[level.lower()]
    except KeyError:
        raise ValueError(f"Invalid level: {level}, expected one of {list(mapping.keys())}")

def confirm_effort(level:str) -> str:
    """
    转换gpt的effort到gemini的thinking level
    """
    valid_levels = ["low", "medium", "high"]
    if level.lower() in valid_levels:
        return level.lower()
    else:
        return None


async def openai_responses_request_to_gemini_payload(
    raw: ResponseCreateParams,
) -> Dict[str, Any]:
    """
    转换OPENAI Responses请求到Gemini API负载格式
    Convert OpenAI Responses API request -> Gemini API payload

    Input:  OpenAI Responses raw request dict
    Output: { "model": str, "request": {...} }  (Gemini API format)
    """

    model = raw["model"]
    contents: List[Dict[str, Any]] = []
    system_instructions: List[str] = []

    # -------------------------
    # 1. instructions -> systemInstruction
    # -------------------------
    if raw.get("instructions"):
        system_instructions.append(str(raw["instructions"]))

    # 新增：input 中 role == "develop" 的 content
    for item in raw.get("input", []):
        if item.get("role") == "developer" and item.get("content"):
            system_instructions.append(str(item["content"]))
    # -------------------------
    # 2. input -> contents
    # -------------------------
    input_data = raw.get("input")

    def convert_input_content(content):
        """
        Responses content -> Gemini parts
        """
        if isinstance(content, str):
            return [{"text": content}]

        if isinstance(content, list):
            parts = []
            for p in content:
                if not isinstance(p, dict):
                    continue

                ptype = p.get("type")

                # text
                if ptype in ("input_text", "text"):
                    parts.append({"text": p.get("text", "")})

                # image
                elif ptype in ("input_image", "input_image", "input_image_url"):
                    url = p.get("image_url")
                    if isinstance(url, dict):
                        url = url.get("url")
                    if not url:
                        url = p.get("url")
                    if url:
                        parts.append(
                            {
                                "inlineData": {
                                    "mimeType": "image/jpeg",
                                    "data": url,  # ⚠️ 如果是 base64，需在上游拆 data URI
                                }
                            }
                        )
            return parts

        return [{"text": str(content)}]

    if isinstance(input_data, str):
        contents.append({"role": "user", "parts": [{"text": input_data}]})

    elif isinstance(input_data, list):
        for item in input_data:
            if isinstance(item, str):
                contents.append({"role": "user", "parts": [{"text": item}]})
                continue

            if not isinstance(item, dict):
                continue

            role = item.get("role", "user")
            if role == "developer": # 对developer兼容
                role = "system"

            if role == "system":
                content = item.get("content")
                if isinstance(content, str):
                    system_instructions.append(content)
                continue

            parts = convert_input_content(item.get("content"))
            if parts:
                contents.append({"role": role, "parts": parts})

    # Gemini 至少需要一个 user message
    if not contents:
        contents.append({"role": "user", "parts": [{"text": ""}]})

    # -------------------------
    # 3. generationConfig
    # -------------------------
    generation_config = {}

    if raw.get("temperature") is not None:
        generation_config["temperature"] = raw["temperature"]

    if raw.get("top_p") is not None:
        generation_config["topP"] = raw["top_p"]

    if raw.get("max_output_tokens") is not None:
        generation_config["maxOutputTokens"] = raw["max_output_tokens"]

    # JSON mode
    text_cfg = raw.get("text") or {}
    fmt = text_cfg.get("format") if isinstance(text_cfg, dict) else None
    if isinstance(fmt, dict) and fmt.get("type") in ("json", "json_object"):
        generation_config["responseMimeType"] = "application/json"

    # -------------------------
    # 4. thinkingConfig Response支持Reasoning，不采用自动配置
    # -------------------------

    # 判断 responses 中是否传入 reason
    include_reason = raw.get("reasoning") is not None

    if include_reason:
        # 进行思考
        effort = raw["reasoning"].get("effort", None)
        if effort is not None:
            if "2.5" in str(model):
                # Gemini 2.5 不支持 thinkingLevel
                generation_config["thinkingConfig"] = {
                    "thinkingBudget" : effort_to_budget(confirm_effort(effort)),
                }
            elif "3" in str(model):
                generation_config["thinkingConfig"] = {
                    "thinkingLevel" : confirm_effort(effort),
                }
    else:
        if "pro" in str(model):
            # Gemini Pro 系列模型无法禁止思考，就自动吧
            generation_config["thinkingConfig"] = {
                "thinkingBudget" : -1,
            }
        else:
            # flash可以不进行思考，设置为0，3系列一样吗...
            generation_config["thinkingConfig"] = {
                "thinkingBudget" : 0,
            }

    # -------------------------
    # 5. tools
    # -------------------------
    request_data: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": generation_config,
        "safetySettings": DEFAULT_SAFETY_SETTINGS,
    }

    if system_instructions:
        request_data["systemInstruction"] = {
            "parts": [{"text": "\n\n".join(system_instructions)}]
        }

    if raw.get("tools"):
        gemini_tools = convert_openai_tools_to_gemini(raw["tools"])
        if gemini_tools:
            request_data["tools"] = gemini_tools

    if raw.get("tool_choice"):
        request_data["toolConfig"] = convert_tool_choice_to_tool_config(raw["tool_choice"])

    # -------------------------
    # 6. search model support
    # -------------------------
    if is_search_model(model):
        if "tools" not in request_data:
            request_data["tools"] = [{"googleSearch": {}}]
        else:
            has_search = any("googleSearch" in t for t in request_data["tools"])
            if not has_search:
                request_data["tools"].append({"googleSearch": {}})

    # 清理 None
    request_data = {k: v for k, v in request_data.items() if v is not None}

    log.debug(
        f"Responses->Gemini prepared: contents={len(contents)}, model={model}"
    )

    return {
        "model": get_base_model_name(model),
        "request": request_data,
    }


import json
import time
import uuid
from fastapi.responses import StreamingResponse
import logging

log = logging.getLogger(__name__)


async def convert_gemini_stream_to_responses_sse(
    gemini_response,
    model: str,
) -> StreamingResponse:
    """
    Gemini StreamingResponse -> OpenAI Responses API SSE
    """
    response_id = f"resp_{uuid.uuid4().hex}"
    created = int(time.time())

    async def sse_generator():
        try:
            # response.created
            yield (
                "event: response.created\n"
                f"data: {json.dumps({'id': response_id, 'model': model, 'created': created})}\n\n"
            ).encode()

            async for chunk in gemini_response.body_iterator:
                if not chunk:
                    continue

                if isinstance(chunk, bytes):
                    if not chunk.startswith(b"data: "):
                        continue
                    payload = chunk[len(b"data: "):].decode()
                else:
                    chunk_str = str(chunk)
                    if not chunk_str.startswith("data: "):
                        continue
                    payload = chunk_str[len("data: "):]

                try:
                    gemini_chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                # === Gemini → Responses 映射 ===
                for candidate in gemini_chunk.get("candidates", []):
                    content = candidate.get("content", {})
                    for part in content.get("parts", []):

                        # ---------- TEXT ----------
                        if "text" in part:
                            event = {
                                "type": "response.output_text.delta",
                                "delta": part["text"],
                            }
                            yield (
                                "event: response.output_text.delta\n"
                                f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
                            ).encode()

                        # ---------- TOOL CALL ----------
                        if "functionCall" in part:
                            fc = part["functionCall"]
                            event = {
                                "type": "response.tool_call.delta",
                                "tool_call": {
                                    "name": fc.get("name"),
                                    "arguments": fc.get("args", {}),
                                },
                            }
                            yield (
                                "event: response.tool_call.delta\n"
                                f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
                            ).encode()

            # response.completed
            completed_event = {
                "type": "response.completed",
                "response": {
                    "id": response_id,
                    "model": model,
                    "created": created,
                    "status": "completed",
                },
            }
            yield (
                "event: response.completed\n"
                f"data: {json.dumps(completed_event, separators=(',', ':'))}\n\n"
            ).encode()

        except Exception as e:
            log.exception("Responses SSE stream error")
            error_event = {
                "type": "response.error",
                "error": {
                    "message": str(e),
                    "code": "stream_error",
                },
            }
            yield (
                "event: response.error\n"
                f"data: {json.dumps(error_event)}\n\n"
            ).encode()

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
