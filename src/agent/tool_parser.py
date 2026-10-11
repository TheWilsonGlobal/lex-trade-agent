"""Tool call extraction and AST parsing utilities for Hermes ReAct loop."""

from __future__ import annotations

import ast
import json
import re
from typing import Any, Callable, Dict, List, Optional


def parse_ast_calls(
    expr_str: str,
    calls_out: List[Dict[str, Any]],
    known_tools: Optional[Dict[str, Callable[..., Any]]] = None,
) -> None:
    """Parse Python-style AST expressions like [screen_entity(name='...', country='...')]"""
    try:
        tree = ast.parse(expr_str.strip(), mode="eval")
        nodes = []
        if isinstance(tree.body, ast.List):
            nodes = tree.body.elts
        elif isinstance(tree.body, ast.Call):
            nodes = [tree.body]
        elif isinstance(tree.body, ast.Tuple):
            nodes = tree.body.elts

        for node in nodes:
            if isinstance(node, ast.Call):
                func_name = node.func.id if isinstance(node.func, ast.Name) else str(node.func)
                kwargs = {}
                for kw in node.keywords:
                    try:
                        kwargs[kw.arg] = ast.literal_eval(kw.value)
                    except Exception:
                        kwargs[kw.arg] = ast.unparse(kw.value) if hasattr(ast, "unparse") else str(kw.value)
                calls_out.append({"name": func_name, "arguments": kwargs})
    except Exception:
        # Fallback regex if AST parsing fails
        func_matches = re.finditer(r"(\b\w+)\((.*?)\)", expr_str)
        for fm in func_matches:
            fname = fm.group(1)
            args_str = fm.group(2)
            kv_matches = re.findall(r"(\w+)\s*=\s*['\"](.*?)['\"]", args_str)
            if kv_matches and (known_tools is None or fname in known_tools):
                calls_out.append({"name": fname, "arguments": dict(kv_matches)})


def extract_tool_calls(
    text: str,
    known_tools: Optional[Dict[str, Callable[..., Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Extract tool calls from multiple model output formats:
    1. Standard XML: <tool_call>{"name": ..., "arguments": ...}</tool_call>
    2. Liquid / Hermes special tokens: <|tool_call_start|>[func(arg='val')]<|tool_call_end|>
    3. Raw JSON: <tool_call>[{...}]</tool_call> or <|tool_call_start|>[{...}]<|tool_call_end|>
    4. Fallback python call expressions: screen_entity(...), etc.
    """
    calls: List[Dict[str, Any]] = []

    # 1. XML format <tool_call>...</tool_call>
    xml_matches = re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL)
    for m in xml_matches:
        m = m.strip()
        # Try JSON parsing
        try:
            parsed = json.loads(m)
            if isinstance(parsed, list):
                calls.extend(parsed)
            elif isinstance(parsed, dict):
                calls.append(parsed)
            continue
        except json.JSONDecodeError:
            pass
        # Try regex cleanup for single quotes
        try:
            cleaned = m.replace("'", '"')
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                calls.extend(parsed)
            elif isinstance(parsed, dict):
                calls.append(parsed)
            continue
        except Exception:
            pass
        # Try Python AST
        parse_ast_calls(m, calls, known_tools)

    # 2. Liquid / Hermes special tokens: <|tool_call_start|>(.*?)<|tool_call_end|>
    lfm_matches = re.findall(r"<\|tool_call_start\|>\s*(.*?)\s*(?:<\|tool_call_end\|>|$)", text, re.DOTALL)
    for block in lfm_matches:
        block = block.strip()
        # Case A: JSON format
        if block.startswith("{") or block.startswith("["):
            try:
                parsed = json.loads(block)
                if isinstance(parsed, list):
                    calls.extend(parsed)
                elif isinstance(parsed, dict):
                    calls.append(parsed)
                continue
            except Exception:
                pass
        # Case B: Python-style expression list: [func(arg=val), ...]
        parse_ast_calls(block, calls, known_tools)

    # 3. Direct pattern fallback if no calls extracted yet
    if not calls:
        direct_matches = re.findall(
            r"(\b(?:screen_entity|lookup_hs_code|verify_dual_use))\((.*?)\)", text, re.DOTALL
        )
        for fname, args_str in direct_matches:
            kv_matches = re.findall(r"(\w+)\s*=\s*['\"](.*?)['\"]", args_str)
            if kv_matches:
                calls.append({"name": fname, "arguments": dict(kv_matches)})

    # Validate extracted calls
    valid_calls = []
    for c in calls:
        if isinstance(c, dict) and "name" in c:
            name = c["name"]
            args = c.get("arguments", {})
            if not isinstance(args, dict):
                args = {}
            valid_calls.append({"name": name, "arguments": args})

    return valid_calls
