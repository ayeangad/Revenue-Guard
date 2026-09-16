"""Thin MCP adapter over ToolRegistry (BYO-AI compat, not a core dependency).

Internal agent calls ToolRegistry directly. External MCP clients (Claude,
ChatGPT, Gemini) go through this adapter: same tools, same stage gates,
same evidence shape. Speaks minimal JSON-RPC over stdio so there is no new
dependency; swap for the official MCP SDK when needed.

Protocol (one JSON object per line on stdin):
  {"id": 1, "method": "tools/list"}
  {"id": 2, "method": "tools/call", "params": {"tool": "get_checkout_metrics", "stage": "TRIAGE"}}
"""
from __future__ import annotations

import json
import sys

READ_TOOLS = ["get_checkout_metrics", "get_conversion_metrics", "get_recent_deploys",
              "get_error_logs", "get_dependency_health", "get_diagnostics",
              "estimate_revenue_impact"]


def list_tools() -> list[dict]:
    return [{"name": t, "stage_gated": True} for t in READ_TOOLS + ["request_approval"]]


def call_tool(tool: str, stage: str = "TRIAGE", **args) -> dict:
    from agent.tools.registry import ToolRegistry
    from agent.tools.sanitize import contains_injection
    for v in args.values():
        if isinstance(v, str) and contains_injection(v):
            return {"error": "blocked: prompt-injection pattern in tool args"}
    reg = ToolRegistry()
    fn = getattr(reg, tool, None)
    if tool not in [t["name"] for t in list_tools()] or fn is None:
        return {"error": f"unknown tool {tool}"}
    try:
        if tool in ("get_diagnostics",):
            payload, ev = fn(args.get("scope", "slow_queries"), stage=stage)
        elif tool == "request_approval":
            payload, ev = fn(args.get("summary", ""), stage=stage)
        elif tool == "estimate_revenue_impact":
            payload, ev = fn(stage=stage)
        else:
            payload, ev = fn(stage=stage)
    except PermissionError as e:
        return {"error": str(e)}
    # JSON-safe: pydantic/detector objects -> str
    return {"payload": json.loads(json.dumps(payload, default=str)),
            "evidence_id": ev.evidence_id, "claim": ev.extracted_claim}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid, method = req.get("id"), req.get("method")
        if method == "tools/list":
            print(json.dumps({"id": rid, "tools": list_tools()}), flush=True)
        elif method == "tools/call":
            p = req.get("params", {})
            print(json.dumps({"id": rid, **call_tool(p.get("tool", ""), p.get("stage", "TRIAGE"),
                                                     **{k: v for k, v in p.items()
                                                        if k not in ("tool", "stage")})}),
                  flush=True)
        else:
            print(json.dumps({"id": rid, "error": "unknown method"}), flush=True)


if __name__ == "__main__":
    main()
