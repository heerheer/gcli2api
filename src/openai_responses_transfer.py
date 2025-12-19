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



import json
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi.responses import StreamingResponse

# 你原来有 log.exception，这里假设你已有 logger
# from your_logger import log


async def convert_gemini_stream_to_responses_sse(
    gemini_response,
    model: str,
) -> StreamingResponse:
    """
    Gemini StreamingResponse -> OpenAI Responses API SSE (best-effort compatible)

    Emits (subset):
      - response.created
      - response.in_progress (periodic)
      - response.output_item.added / response.output_item.done
      - response.content_part.added / response.content_part.done
      - response.output_text.delta / response.output_text.done
      - response.function_call_arguments.delta / response.function_call_arguments.done
      - response.completed
      - error
    """
    response_id = f"resp_{uuid.uuid4().hex}"
    created_at = int(time.time())

    seq = 0  # sequence_number must be monotonic increasing

    # Track output items to build response.completed payload
    output_items: List[Dict[str, Any]] = []
    next_output_index = 0

    # Track the single assistant message item for streaming text (created lazily)
    msg_item_id: Optional[str] = None
    msg_output_index: Optional[int] = None
    msg_text_buf: List[str] = []

    def _next_seq() -> int:
        nonlocal seq
        seq += 1
        return seq

    def _sse(event_type: str, data_obj: Dict[str, Any]) -> bytes:
        # SSE line "event:" is optional for some clients but we emit it
        return (
            f"event: {event_type}\n"
            f"data: {json.dumps(data_obj, separators=(',', ':'))}\n\n"
        ).encode("utf-8")

    def _base_response(status: str) -> Dict[str, Any]:
        # Keep it minimal but aligned with docs field names
        return {
            "id": response_id,
            "object": "response",
            "created_at": created_at,
            "status": status,
            "error": None,
            "model": model,
            "output": [],  # for streaming events we can keep empty; completed will include full
        }

    def _ensure_message_started() -> List[bytes]:
        """
        Create assistant message output item and its first content part.
        """
        nonlocal msg_item_id, msg_output_index, next_output_index

        if msg_item_id is not None:
            return []

        msg_item_id = f"msg_{uuid.uuid4().hex}"
        msg_output_index = next_output_index
        next_output_index += 1

        events: List[bytes] = []

        # response.output_item.added (message)
        item_added = {
            "type": "response.output_item.added",
            "output_index": msg_output_index,
            "item": {
                "id": msg_item_id,
                "status": "in_progress",
                "type": "message",
                "role": "assistant",
                "content": [],
            },
            "sequence_number": _next_seq(),
        }
        events.append(_sse("response.output_item.added", item_added))

        # response.content_part.added (output_text part)
        part_added = {
            "type": "response.content_part.added",
            "item_id": msg_item_id,
            "output_index": msg_output_index,
            "content_index": 0,
            "part": {"type": "output_text", "text": "", "annotations": []},
            "sequence_number": _next_seq(),
        }
        events.append(_sse("response.content_part.added", part_added))

        return events

    def _finalize_message_if_any() -> List[bytes]:
        """
        Close out text content + message item with done events.
        """
        if msg_item_id is None or msg_output_index is None:
            return []

        final_text = "".join(msg_text_buf)

        # output_text.done
        events: List[bytes] = []
        events.append(
            _sse(
                "response.output_text.done",
                {
                    "type": "response.output_text.done",
                    "item_id": msg_item_id,
                    "output_index": msg_output_index,
                    "content_index": 0,
                    "text": final_text,
                    "sequence_number": _next_seq(),
                },
            )
        )

        # content_part.done
        events.append(
            _sse(
                "response.content_part.done",
                {
                    "type": "response.content_part.done",
                    "item_id": msg_item_id,
                    "output_index": msg_output_index,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": final_text, "annotations": []},
                    "sequence_number": _next_seq(),
                },
            )
        )

        # output_item.done (message)
        msg_item = {
            "id": msg_item_id,
            "status": "completed",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": final_text, "annotations": []}],
        }
        events.append(
            _sse(
                "response.output_item.done",
                {
                    "type": "response.output_item.done",
                    "output_index": msg_output_index,
                    "item": msg_item,
                    "sequence_number": _next_seq(),
                },
            )
        )

        # store in completed response output in the correct slot
        output_items.append((msg_output_index, msg_item))

        return events

    def _emit_function_call(fc_name: Optional[str], fc_args_obj: Any) -> List[bytes]:
        """
        Emit a function_call output item + its arguments delta/done + item.done.

        In Responses output array, tool calls are items with:
          type == "function_call"
          name, arguments (string), call_id
        """
        nonlocal next_output_index

        output_index = next_output_index
        next_output_index += 1

        item_id = f"fc_{uuid.uuid4().hex}"
        call_id = f"call_{uuid.uuid4().hex}"
        name = fc_name or "unknown_function"

        # arguments must be a string (JSON string)
        try:
            arguments_str = json.dumps(fc_args_obj, separators=(",", ":"), ensure_ascii=False)
        except Exception:
            arguments_str = json.dumps({"_raw": str(fc_args_obj)}, separators=(",", ":"), ensure_ascii=False)

        events: List[bytes] = []

        # output_item.added (function_call)
        events.append(
            _sse(
                "response.output_item.added",
                {
                    "type": "response.output_item.added",
                    "output_index": output_index,
                    "item": {
                        "id": item_id,
                        "status": "in_progress",
                        "type": "function_call",
                        "name": name,
                        "arguments": "",
                        "call_id": call_id,
                    },
                    "sequence_number": _next_seq(),
                },
            )
        )

        # function_call_arguments.delta (we send it in one shot)
        events.append(
            _sse(
                "response.function_call_arguments.delta",
                {
                    "type": "response.function_call_arguments.delta",
                    "item_id": item_id,
                    "output_index": output_index,
                    "delta": arguments_str,
                    "sequence_number": _next_seq(),
                },
            )
        )

        # function_call_arguments.done
        events.append(
            _sse(
                "response.function_call_arguments.done",
                {
                    "type": "response.function_call_arguments.done",
                    "item_id": item_id,
                    "output_index": output_index,
                    "name": name,
                    "arguments": arguments_str,
                    "sequence_number": _next_seq(),
                },
            )
        )

        # output_item.done (function_call)
        fc_item = {
            "id": item_id,
            "status": "completed",
            "type": "function_call",
            "name": name,
            "arguments": arguments_str,
            "call_id": call_id,
        }
        events.append(
            _sse(
                "response.output_item.done",
                {
                    "type": "response.output_item.done",
                    "output_index": output_index,
                    "item": fc_item,
                    "sequence_number": _next_seq(),
                },
            )
        )

        output_items.append((output_index, fc_item))
        return events

    async def _iter_gemini_sse_json() -> AsyncIterator[Dict[str, Any]]:
        """
        Parse upstream SSE lines: expects "data: <json>" chunks.
        """
        async for chunk in gemini_response.body_iterator:
            if not chunk:
                continue

            if isinstance(chunk, bytes):
                b = chunk.strip()
                if not b.startswith(b"data:"):
                    continue
                payload = b[len(b"data:") :].strip().decode("utf-8", errors="ignore")
            else:
                s = str(chunk).strip()
                if not s.startswith("data:"):
                    continue
                payload = s[len("data:") :].strip()

            if payload == "[DONE]":
                return

            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue

            if isinstance(obj, dict):
                yield obj

    async def sse_generator():
        try:
            # response.created
            created_event = {
                "type": "response.created",
                "response": _base_response("in_progress"),
                "sequence_number": _next_seq(),
            }
            yield _sse("response.created", created_event)

            # response.in_progress (at least once early)
            inprog_event = {
                "type": "response.in_progress",
                "response": _base_response("in_progress"),
                "sequence_number": _next_seq(),
            }
            yield _sse("response.in_progress", inprog_event)

            async for gemini_chunk in _iter_gemini_sse_json():
                # optional: emit periodic in_progress (lightweight heartbeat)
                yield _sse(
                    "response.in_progress",
                    {
                        "type": "response.in_progress",
                        "response": _base_response("in_progress"),
                        "sequence_number": _next_seq(),
                    },
                )

                for candidate in gemini_chunk.get("candidates", []) or []:
                    content = candidate.get("content") or {}
                    for part in content.get("parts", []) or []:
                        # TEXT
                        if "text" in part and isinstance(part["text"], str) and part["text"]:
                            # ensure message + content part exists
                            for ev in _ensure_message_started():
                                yield ev

                            delta = part["text"]
                            msg_text_buf.append(delta)

                            yield _sse(
                                "response.output_text.delta",
                                {
                                    "type": "response.output_text.delta",
                                    "item_id": msg_item_id,
                                    "output_index": msg_output_index,
                                    "content_index": 0,
                                    "delta": delta,
                                    "sequence_number": _next_seq(),
                                },
                            )

                        # FUNCTION CALL
                        if "functionCall" in part and isinstance(part["functionCall"], dict):
                            fc = part["functionCall"]
                            fc_name = fc.get("name")
                            fc_args = fc.get("args", {})
                            for ev in _emit_function_call(fc_name, fc_args):
                                yield ev

            # finalize text message (if any)
            for ev in _finalize_message_if_any():
                yield ev

            # Build completed response.output in correct order
            completed_output: List[Dict[str, Any]] = []
            for _, item in sorted(output_items, key=lambda t: t[0]):
                completed_output.append(item)

            completed_event = {
                "type": "response.completed",
                "response": {
                    **_base_response("completed"),
                    "output": completed_output,
                },
                "sequence_number": _next_seq(),
            }
            yield _sse("response.completed", completed_event)

        except Exception as e:
            # log.exception("Responses SSE stream error")
            yield _sse(
                "error",
                {
                    "type": "error",
                    "code": "stream_error",
                    "message": str(e),
                    "param": None,
                    "sequence_number": _next_seq(),
                },
            )

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
