"""Compress long chat sessions into a rolling summary for the coach agent."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm
from bootstrap import get_repo

# Soft budget for model-facing context (summary + recent raw messages).
CHAR_BUDGET = 16_000
# Compress when more than this many messages are not yet in the summary.
UNSUMMARIZED_LIMIT = 80
# Always keep this many newest user turns (plus their tool traces) as raw history.
KEEP_RECENT_TURNS = 6
# Absolute fallback: keep this many newest user turns if summarization lags.
FALLBACK_KEEP_TURNS = 8

SUMMARY_PROMPT = """你是对话压缩助手。把健身教练与用户的较早对话压成一段中文摘要，供后续教练继续服务。

要求：
1. 只输出摘要正文：无标题、无 markdown、无前后解释。
2. 必须保留：目标与期限、伤病/禁忌、饮食偏好与忌口、已定热量/宏量目标、当前周计划结构、用户明确要求、未完成约定。
3. 若片段里有工具调用，记下「调了什么、是否 ok」；不要把教练口头提议当成已写库。
4. 省略寒暄、重复确认、已过时的临时安排；控制在 500 字以内。
5. 若已有旧摘要：与新片段合并成一份连贯摘要，不要简单首尾拼接。
"""


def _role_label(role: str) -> str:
    if role == "user":
        return "用户"
    if role == "assistant":
        return "教练"
    return role or "?"


def _row_meta(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("meta_json")
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _user_turn_count(rows: list[dict[str, Any]]) -> int:
    return sum(1 for r in rows if r.get("role") == "user")


def _slice_recent_turns(rows: list[dict[str, Any]], n_turns: int) -> list[dict[str, Any]]:
    user_idxs = [i for i, r in enumerate(rows) if r.get("role") == "user"]
    if not user_idxs or len(user_idxs) <= n_turns:
        return list(rows)
    return list(rows[user_idxs[-n_turns] :])


def _format_transcript(rows: list[dict[str, Any]]) -> str:
    lines = []
    for row in rows:
        role = str(row.get("role") or "")
        content = (row.get("content") or "").strip()
        meta = _row_meta(row)
        if role == "tool":
            name = str(meta.get("name") or "tool")
            snippet = content.replace("\n", " ")
            if len(snippet) > 240:
                snippet = snippet[:240] + "…"
            lines.append(f"工具[{name}]：{snippet}")
            continue
        if role == "assistant":
            tool_calls = meta.get("tool_calls") or []
            if isinstance(tool_calls, list) and tool_calls:
                names = []
                for tc in tool_calls:
                    if isinstance(tc, dict) and tc.get("name"):
                        names.append(str(tc["name"]))
                if names:
                    lines.append("教练调用工具：" + ",".join(names))
            if content:
                lines.append(f"教练：{content}")
            continue
        if not content:
            continue
        lines.append(f"{_role_label(role)}：{content}")
    return "\n".join(lines)


def _estimate_chars(summary: str, rows: list[dict[str, Any]]) -> int:
    return len(summary or "") + sum(len(r.get("content") or "") for r in rows)


def build_model_history(
    session: dict[str, Any],
    all_messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Return (summary_text, message rows to send as raw history)."""
    summary = (session.get("summary") or "").strip()
    upto = session.get("summary_upto_id")
    if upto is not None:
        recent = [m for m in all_messages if int(m["id"]) > int(upto)]
    else:
        recent = list(all_messages)

    # Safety: never send unbounded raw history even if summary lags.
    recent = _slice_recent_turns(recent, FALLBACK_KEEP_TURNS)
    return summary, recent


def _needs_compress(summary: str, unsummarized: list[dict[str, Any]]) -> bool:
    if _user_turn_count(unsummarized) <= KEEP_RECENT_TURNS:
        return False
    if len(unsummarized) > UNSUMMARIZED_LIMIT:
        return True
    return _estimate_chars(summary, unsummarized) > CHAR_BUDGET


def _summarize(old_summary: str, to_compress: list[dict[str, Any]]) -> str:
    transcript = _format_transcript(to_compress)
    if not transcript.strip():
        return (old_summary or "").strip()

    user_parts = []
    if old_summary.strip():
        user_parts.append("【旧摘要】\n" + old_summary.strip())
    user_parts.append("【需压缩的对话】\n" + transcript)
    llm = get_llm(temperature=0.2, streaming=False, thinking=False)
    resp = llm.invoke(
        [
            SystemMessage(content=SUMMARY_PROMPT),
            HumanMessage(content="\n\n".join(user_parts)),
        ]
    )
    text = getattr(resp, "content", resp)
    if isinstance(text, list):
        parts = []
        for block in text:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            else:
                parts.append(str(block))
        text = "\n".join(parts)
    return str(text or "").strip() or (old_summary or "").strip()


def ensure_context_budget(session_id: int) -> dict[str, Any]:
    """Compress older messages into session.summary when over budget.

    UI history is unchanged; only model-facing context shrinks.
    On failure, leaves DB as-is (caller may still truncate).
    """
    repo = get_repo()
    session = repo.get_chat_session(session_id)
    if not session:
        return {"ok": False, "compressed": False, "reason": "missing_session"}

    all_messages = repo.get_all_chat_messages(session_id)
    summary = (session.get("summary") or "").strip()
    upto = session.get("summary_upto_id")
    if upto is not None:
        unsummarized = [m for m in all_messages if int(m["id"]) > int(upto)]
    else:
        unsummarized = list(all_messages)

    if not _needs_compress(summary, unsummarized):
        return {
            "ok": True,
            "compressed": False,
            "summary": summary,
            "unsummarized": len(unsummarized),
        }

    keep = _slice_recent_turns(unsummarized, KEEP_RECENT_TURNS)
    to_compress = unsummarized[: max(0, len(unsummarized) - len(keep))]
    if not to_compress:
        return {"ok": True, "compressed": False, "summary": summary}

    try:
        new_summary = _summarize(summary, to_compress)
        upto_id = int(to_compress[-1]["id"])
        repo.update_chat_session_summary(session_id, new_summary, upto_id)
        return {
            "ok": True,
            "compressed": True,
            "summary": new_summary,
            "summary_upto_id": upto_id,
            "compressed_count": len(to_compress),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "compressed": False,
            "error": str(exc),
            "summary": summary,
        }
