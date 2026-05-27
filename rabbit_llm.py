#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rabbit_llm.py — RabbitOS Multi-Provider LLM Bridge
===================================================
Zero-API-key LLM access for Chase Allen Ringquist.
Auto-detects available providers and falls back in priority order:

  1. Ollama          localhost:11434  — FREE, local, offline-capable
  2. Groq            api.groq.com     — FREE tier (30 req/min, no card)
  3. Google Gemini   generativelanguage.googleapis.com — FREE (1M tok/day)
  4. HuggingFace     api-inference.huggingface.co — FREE tier
  5. OpenRouter      openrouter.ai    — FREE models available
  6. Anthropic       api.anthropic.com — paid, used if key present

All providers are normalized to the same internal interface.
Tool-use is supported on Ollama (llama3.2+), Groq, Gemini, and Anthropic.

Usage:
  from rabbit_llm import get_llm, LLMBridge

  llm = get_llm()
  response = llm.chat([{"role": "user", "content": "What's 2+2?"}])
  print(response["text"])

  # With tools
  response = llm.chat(messages, tools=[{...}])
  if response["tool_calls"]:
      for tc in response["tool_calls"]:
          print(tc["name"], tc["input"])
"""

from __future__ import annotations
import base64, hashlib, json, os, re, socket, sqlite3, threading, time
import urllib.error, urllib.parse, urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ─── Identity ─────────────────────────────────────────────────────────────────
TWIN_UUID = "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba"
TWIN_NAME = "Chase Allen Ringquist"

LLM_DB  = Path(__file__).parent / "rabbit_llm.db"
LLM_LOG = Path(__file__).parent / "rabbit_llm.log"


def _log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] [LLM] {msg}"
    print(line, flush=True)
    try:
        with open(LLM_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ─── Normalized response ──────────────────────────────────────────────────────
@dataclass
class LLMResponse:
    text:        str   = ""
    tool_calls:  List[Dict] = field(default_factory=list)
    stop_reason: str   = "end_turn"
    provider:    str   = ""
    model:       str   = ""
    tokens_in:   int   = 0
    tokens_out:  int   = 0
    latency_ms:  float = 0.0
    raw:         Any   = None
    error:       str   = ""

    def ok(self) -> bool:
        return not self.error

    def has_tools(self) -> bool:
        return bool(self.tool_calls)


# ──────────────────────────────────────────────────────────────────────────────
# PROVIDER: Ollama (localhost — FREE, offline-capable)
# ──────────────────────────────────────────────────────────────────────────────
class OllamaProvider:
    """
    Ollama local LLM. Supports llama3.2, mistral, phi3, gemma, etc.
    Tool use supported with llama3.2+.
    No API key required.
    """
    BASE_URL = "http://localhost:11434"
    NAME     = "ollama"

    # Models in preference order (first available wins)
    PREFERRED_MODELS = [
        "llama3.2:latest",
        "llama3.1:latest",
        "llama3:latest",
        "mistral:latest",
        "phi3:latest",
        "gemma2:latest",
        "qwen2.5:latest",
        "llama3.2:3b",
    ]

    def __init__(self, model: str = ""):
        self._model     = model
        self._available = False
        self._lock      = threading.Lock()

    def _req(self, path: str, body: Dict, timeout: int = 120) -> Dict:
        data = json.dumps(body).encode()
        req  = urllib.request.Request(
            f"{self.BASE_URL}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            return json.loads(resp.read())
        except Exception as e:
            return {"error": str(e)[:120]}

    def detect(self) -> Tuple[bool, str]:
        """Check if Ollama is running and return best available model."""
        try:
            resp = urllib.request.urlopen(
                f"{self.BASE_URL}/api/tags", timeout=2)
            data    = json.loads(resp.read())
            models  = [m["name"] for m in data.get("models", [])]
            if not models:
                return False, ""
            # Pick best available from preferred list
            for pref in self.PREFERRED_MODELS:
                for m in models:
                    if pref.split(":")[0] in m:
                        return True, m
            return True, models[0]  # fallback to first available
        except Exception:
            return False, ""

    def _to_ollama_tools(self, tools: List[Dict]) -> List[Dict]:
        """Convert Anthropic-style tools to Ollama/OpenAI function format."""
        ollama_tools = []
        for t in tools:
            ollama_tools.append({
                "type": "function",
                "function": {
                    "name":        t["name"],
                    "description": t.get("description", ""),
                    "parameters":  t.get("input_schema", {
                        "type": "object", "properties": {}
                    }),
                }
            })
        return ollama_tools

    def _to_ollama_messages(self, messages: List[Dict]) -> List[Dict]:
        """Normalize messages to Ollama format."""
        out = []
        for msg in messages:
            role    = msg["role"]
            content = msg["content"]

            if isinstance(content, str):
                out.append({"role": role, "content": content})
            elif isinstance(content, list):
                # Handle Anthropic-style content blocks
                text_parts = []
                tool_results = []
                for block in content:
                    if isinstance(block, dict):
                        btype = block.get("type", "")
                        if btype == "text":
                            text_parts.append(block.get("text", ""))
                        elif btype == "tool_result":
                            tool_results.append({
                                "role":    "tool",
                                "content": str(block.get("content", ""))[:2000],
                                "tool_call_id": block.get("tool_use_id", ""),
                            })
                        elif btype == "tool_use":
                            # assistant tool call block — handled via tool_calls
                            pass
                if text_parts:
                    out.append({"role": role, "content": "\n".join(text_parts)})
                out.extend(tool_results)
            else:
                out.append({"role": role, "content": str(content)})
        return out

    def chat(self, messages: List[Dict], tools: List[Dict] = None,
             system: str = "", model: str = "") -> LLMResponse:
        t0      = time.time()
        model   = model or self._model
        if not model:
            ok, model = self.detect()
            if not ok:
                return LLMResponse(error="Ollama not running", provider=self.NAME)
            self._model = model

        ollama_messages = self._to_ollama_messages(messages)
        if system:
            ollama_messages = [{"role": "system", "content": system}] + ollama_messages

        body: Dict[str, Any] = {
            "model":  model,
            "messages": ollama_messages,
            "stream": False,
            "options": {"temperature": 0.3, "num_ctx": 8192},
        }
        if tools:
            body["tools"] = self._to_ollama_tools(tools)

        raw = self._req("/api/chat", body, timeout=180)
        if "error" in raw:
            return LLMResponse(error=raw["error"], provider=self.NAME, model=model)

        resp_msg   = raw.get("message", {})
        text       = resp_msg.get("content", "") or ""
        tool_calls = []

        # Parse tool calls from Ollama response
        for tc in (resp_msg.get("tool_calls") or []):
            fn   = tc.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"raw": args}
            tool_calls.append({
                "id":    tc.get("id", hashlib.md5(fn.get("name","").encode()).hexdigest()[:8]),
                "name":  fn.get("name", ""),
                "input": args,
            })

        usage    = raw.get("usage", {}) or {}
        stop_map = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens"}
        stop     = stop_map.get(raw.get("done_reason", "stop"), "end_turn")

        return LLMResponse(
            text        = text,
            tool_calls  = tool_calls,
            stop_reason = "tool_use" if tool_calls else stop,
            provider    = self.NAME,
            model       = model,
            tokens_in   = usage.get("prompt_tokens", 0),
            tokens_out  = usage.get("completion_tokens", 0),
            latency_ms  = round((time.time() - t0) * 1000, 1),
            raw         = raw,
        )

    def pull_model(self, model: str = "llama3.2") -> bool:
        """Pull a model if not present (runs in background)."""
        _log(f"[Ollama] Pulling model: {model} ...")
        body = json.dumps({"name": model}).encode()
        req  = urllib.request.Request(
            f"{self.BASE_URL}/api/pull", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                for line in resp:
                    try:
                        d = json.loads(line)
                        status = d.get("status", "")
                        if status:
                            _log(f"[Ollama:pull] {model}: {status}")
                    except Exception:
                        pass
            return True
        except Exception as e:
            _log(f"[Ollama:pull] {model} failed: {e}")
            return False

    def list_models(self) -> List[str]:
        try:
            resp = urllib.request.urlopen(
                f"{self.BASE_URL}/api/tags", timeout=3)
            data = json.loads(resp.read())
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []


# ──────────────────────────────────────────────────────────────────────────────
# PROVIDER: Groq (FREE tier — Llama 3.3 70B, no credit card)
# ──────────────────────────────────────────────────────────────────────────────
class GroqProvider:
    """
    Groq free tier: llama-3.3-70b-versatile, llama-3.1-8b-instant.
    30 req/min, 14,400 req/day. Sign up at console.groq.com (no card).
    Set GROQ_API_KEY env var.
    """
    BASE_URL  = "https://api.groq.com/openai/v1"
    NAME      = "groq"
    FREE_MODEL= "llama-3.3-70b-versatile"

    def __init__(self, api_key: str = ""):
        self._key = api_key or os.environ.get("GROQ_API_KEY", "")

    def detect(self) -> bool:
        return bool(self._key)

    def _req(self, path: str, body: Dict, timeout: int = 60) -> Dict:
        data = json.dumps(body).encode()
        req  = urllib.request.Request(
            f"{self.BASE_URL}{path}", data=data,
            headers={"Authorization": f"Bearer {self._key}",
                     "Content-Type":  "application/json"},
            method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
        except Exception as e:
            return {"error": str(e)[:120]}

    def _to_openai_tools(self, tools: List[Dict]) -> List[Dict]:
        result = []
        for t in tools:
            result.append({
                "type": "function",
                "function": {
                    "name":        t["name"],
                    "description": t.get("description", ""),
                    "parameters":  t.get("input_schema",
                                        {"type": "object", "properties": {}}),
                }
            })
        return result

    def _normalize_messages(self, messages: List[Dict],
                             system: str = "") -> List[Dict]:
        out = []
        if system:
            out.append({"role": "system", "content": system})
        for msg in messages:
            role    = msg["role"]
            content = msg["content"]
            if isinstance(content, str):
                out.append({"role": role, "content": content})
            elif isinstance(content, list):
                text_parts   = []
                tool_results = []
                tool_calls   = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type", "")
                    if btype == "text":
                        text_parts.append(block.get("text", ""))
                    elif btype == "tool_use":
                        tool_calls.append({
                            "id":   block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name":      block.get("name", ""),
                                "arguments": json.dumps(block.get("input", {})),
                            }
                        })
                    elif btype == "tool_result":
                        tool_results.append({
                            "role":         "tool",
                            "tool_call_id": block.get("tool_use_id", ""),
                            "content":      str(block.get("content", ""))[:2000],
                        })
                if tool_calls:
                    entry: Dict[str, Any] = {"role": "assistant"}
                    if text_parts:
                        entry["content"] = "\n".join(text_parts)
                    entry["tool_calls"] = tool_calls
                    out.append(entry)
                elif text_parts:
                    out.append({"role": role,
                                "content": "\n".join(text_parts)})
                out.extend(tool_results)
        return out

    def chat(self, messages: List[Dict], tools: List[Dict] = None,
             system: str = "", model: str = "") -> LLMResponse:
        if not self._key:
            return LLMResponse(error="GROQ_API_KEY not set", provider=self.NAME)
        t0    = time.time()
        model = model or self.FREE_MODEL

        body: Dict[str, Any] = {
            "model":       model,
            "messages":    self._normalize_messages(messages, system),
            "max_tokens":  4096,
            "temperature": 0.3,
        }
        if tools:
            body["tools"]       = self._to_openai_tools(tools)
            body["tool_choice"] = "auto"

        raw = self._req("/chat/completions", body)
        if "error" in raw:
            return LLMResponse(error=raw["error"], provider=self.NAME, model=model)

        choice     = (raw.get("choices") or [{}])[0]
        msg        = choice.get("message", {})
        text       = msg.get("content", "") or ""
        tool_calls = []
        for tc in (msg.get("tool_calls") or []):
            fn   = tc.get("function", {})
            args = fn.get("arguments", "{}")
            try:
                args = json.loads(args)
            except Exception:
                args = {"raw": args}
            tool_calls.append({
                "id":    tc.get("id", ""),
                "name":  fn.get("name", ""),
                "input": args,
            })
        usage  = raw.get("usage", {})
        finish = choice.get("finish_reason", "stop")
        stop   = "tool_use" if tool_calls else ("end_turn" if finish == "stop" else finish)

        return LLMResponse(
            text        = text,
            tool_calls  = tool_calls,
            stop_reason = stop,
            provider    = self.NAME,
            model       = model,
            tokens_in   = usage.get("prompt_tokens", 0),
            tokens_out  = usage.get("completion_tokens", 0),
            latency_ms  = round((time.time() - t0) * 1000, 1),
            raw         = raw,
        )


# ──────────────────────────────────────────────────────────────────────────────
# PROVIDER: Google Gemini (FREE — 1M tokens/day, 15 RPM)
# ──────────────────────────────────────────────────────────────────────────────
class GeminiProvider:
    """
    Google Gemini free tier: gemini-1.5-flash.
    15 RPM, 1M TPD — very generous.
    Get free key at aistudio.google.com (no card).
    Set GEMINI_API_KEY env var.
    """
    BASE_URL   = "https://generativelanguage.googleapis.com/v1beta"
    NAME       = "gemini"
    FREE_MODEL = "gemini-1.5-flash"

    def __init__(self, api_key: str = ""):
        self._key = api_key or os.environ.get("GEMINI_API_KEY", "")

    def detect(self) -> bool:
        return bool(self._key)

    def _req(self, path: str, body: Dict, timeout: int = 60) -> Dict:
        url  = f"{self.BASE_URL}{path}?key={self._key}"
        data = json.dumps(body).encode()
        req  = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
        except Exception as e:
            return {"error": str(e)[:120]}

    def _to_gemini_tools(self, tools: List[Dict]) -> List[Dict]:
        fn_decls = []
        for t in tools:
            schema = t.get("input_schema", {})
            # Gemini doesn't allow $schema or additionalProperties
            clean_schema = {
                "type":       schema.get("type", "object"),
                "properties": schema.get("properties", {}),
            }
            if schema.get("required"):
                clean_schema["required"] = schema["required"]
            fn_decls.append({
                "name":        t["name"],
                "description": t.get("description", ""),
                "parameters":  clean_schema,
            })
        return [{"functionDeclarations": fn_decls}]

    def _to_gemini_messages(self, messages: List[Dict],
                             system: str = "") -> Tuple[List[Dict], str]:
        contents = []
        sys_inst = system

        for msg in messages:
            role    = msg["role"]
            content = msg["content"]
            gemini_role = "user" if role == "user" else "model"

            if isinstance(content, str):
                if content.strip():
                    contents.append({
                        "role": gemini_role,
                        "parts": [{"text": content}]
                    })
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type", "")
                    if btype == "text" and block.get("text", "").strip():
                        parts.append({"text": block["text"]})
                    elif btype == "tool_use":
                        parts.append({
                            "functionCall": {
                                "name": block.get("name", ""),
                                "args": block.get("input", {}),
                            }
                        })
                    elif btype == "tool_result":
                        # Gemini expects function response as model turn
                        contents.append({
                            "role": "user",
                            "parts": [{
                                "functionResponse": {
                                    "name":     block.get("tool_use_id", "fn"),
                                    "response": {"result": str(block.get("content",""))[:1000]},
                                }
                            }]
                        })
                if parts:
                    contents.append({"role": gemini_role, "parts": parts})

        return contents, sys_inst

    def chat(self, messages: List[Dict], tools: List[Dict] = None,
             system: str = "", model: str = "") -> LLMResponse:
        if not self._key:
            return LLMResponse(error="GEMINI_API_KEY not set", provider=self.NAME)
        t0    = time.time()
        model = model or self.FREE_MODEL

        contents, sys_inst = self._to_gemini_messages(messages, system)
        body: Dict[str, Any] = {
            "contents":         contents,
            "generationConfig": {"maxOutputTokens": 4096, "temperature": 0.3},
        }
        if sys_inst:
            body["systemInstruction"] = {"parts": [{"text": sys_inst}]}
        if tools:
            body["tools"] = self._to_gemini_tools(tools)

        raw = self._req(f"/models/{model}:generateContent", body)
        if "error" in raw:
            return LLMResponse(error=raw["error"], provider=self.NAME, model=model)

        candidates = raw.get("candidates", [])
        if not candidates:
            return LLMResponse(
                error="no candidates in response", provider=self.NAME, model=model)

        parts      = candidates[0].get("content", {}).get("parts", [])
        text       = ""
        tool_calls = []
        for part in parts:
            if "text" in part:
                text += part["text"]
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append({
                    "id":    hashlib.md5(fc.get("name","").encode()).hexdigest()[:8],
                    "name":  fc.get("name", ""),
                    "input": fc.get("args", {}),
                })

        usage   = raw.get("usageMetadata", {})
        stop    = "tool_use" if tool_calls else "end_turn"

        return LLMResponse(
            text        = text,
            tool_calls  = tool_calls,
            stop_reason = stop,
            provider    = self.NAME,
            model       = model,
            tokens_in   = usage.get("promptTokenCount", 0),
            tokens_out  = usage.get("candidatesTokenCount", 0),
            latency_ms  = round((time.time() - t0) * 1000, 1),
            raw         = raw,
        )


# ──────────────────────────────────────────────────────────────────────────────
# PROVIDER: HuggingFace Inference API (FREE tier)
# ──────────────────────────────────────────────────────────────────────────────
class HuggingFaceProvider:
    """
    HuggingFace free inference. No tool use but works for text generation.
    Set HF_TOKEN env var (free account).
    """
    BASE_URL   = "https://api-inference.huggingface.co/models"
    NAME       = "huggingface"
    FREE_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"

    def __init__(self, token: str = ""):
        self._token = token or os.environ.get("HF_TOKEN", "")

    def detect(self) -> bool:
        return bool(self._token)

    def chat(self, messages: List[Dict], tools: List[Dict] = None,
             system: str = "", model: str = "") -> LLMResponse:
        if not self._token:
            return LLMResponse(error="HF_TOKEN not set", provider=self.NAME)
        t0    = time.time()
        model = model or self.FREE_MODEL

        # Build prompt from messages
        prompt = ""
        if system:
            prompt += f"<s>[INST] {system} [/INST]\n"
        for msg in messages:
            role = msg["role"]
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text")
            if role == "user":
                prompt += f"[INST] {content} [/INST]"
            else:
                prompt += f" {content} </s>"

        body = json.dumps({
            "inputs":     prompt,
            "parameters": {"max_new_tokens": 1024, "temperature": 0.3,
                            "return_full_text": False},
        }).encode()
        req  = urllib.request.Request(
            f"{self.BASE_URL}/{model}",
            data=body,
            headers={"Authorization": f"Bearer {self._token}",
                     "Content-Type":  "application/json"},
            method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            raw  = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return LLMResponse(
                error=f"HTTP {e.code}: {e.read().decode()[:100]}",
                provider=self.NAME, model=model)
        except Exception as e:
            return LLMResponse(error=str(e)[:120], provider=self.NAME, model=model)

        if isinstance(raw, list):
            text = raw[0].get("generated_text", "") if raw else ""
        elif isinstance(raw, dict):
            text = raw.get("generated_text", "")
        else:
            text = str(raw)

        return LLMResponse(
            text       = text,
            stop_reason= "end_turn",
            provider   = self.NAME,
            model      = model,
            latency_ms = round((time.time() - t0) * 1000, 1),
            raw        = raw,
        )


# ──────────────────────────────────────────────────────────────────────────────
# PROVIDER: Anthropic (paid, fallback of last resort)
# ──────────────────────────────────────────────────────────────────────────────
class AnthropicProvider:
    BASE_URL  = "https://api.anthropic.com/v1"
    NAME      = "anthropic"
    MODEL     = "claude-sonnet-4-6"

    def __init__(self, api_key: str = ""):
        self._key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def detect(self) -> bool:
        return bool(self._key)

    def chat(self, messages: List[Dict], tools: List[Dict] = None,
             system: str = "", model: str = "") -> LLMResponse:
        if not self._key:
            return LLMResponse(error="ANTHROPIC_API_KEY not set", provider=self.NAME)
        t0    = time.time()
        model = model or self.MODEL

        body: Dict[str, Any] = {
            "model":      model,
            "max_tokens": 4096,
            "messages":   messages,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = tools

        data = json.dumps(body).encode()
        req  = urllib.request.Request(
            f"{self.BASE_URL}/messages", data=data,
            headers={"x-api-key": self._key,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            raw  = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return LLMResponse(
                error=f"HTTP {e.code}: {e.read().decode()[:200]}",
                provider=self.NAME, model=model)
        except Exception as e:
            return LLMResponse(error=str(e)[:200], provider=self.NAME, model=model)

        content     = raw.get("content", [])
        text        = ""
        tool_calls  = []
        for block in content:
            if block.get("type") == "text":
                text += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id":    block.get("id", ""),
                    "name":  block.get("name", ""),
                    "input": block.get("input", {}),
                })
        stop = raw.get("stop_reason", "end_turn")
        if tool_calls:
            stop = "tool_use"
        usage = raw.get("usage", {})

        return LLMResponse(
            text        = text,
            tool_calls  = tool_calls,
            stop_reason = stop,
            provider    = self.NAME,
            model       = model,
            tokens_in   = usage.get("input_tokens", 0),
            tokens_out  = usage.get("output_tokens", 0),
            latency_ms  = round((time.time() - t0) * 1000, 1),
            raw         = raw,
        )


# ──────────────────────────────────────────────────────────────────────────────
# LLM BRIDGE — auto-detect, fallback, agentic tool loop
# ──────────────────────────────────────────────────────────────────────────────
class LLMBridge:
    """
    Unified LLM interface for RabbitOS.
    Auto-detects available providers in priority order:
      Ollama → Groq → Gemini → HuggingFace → Anthropic

    Supports agentic tool-use loop compatible with rabbit_nettools BrowserAssistant.
    """

    SYSTEM = (
        f"You are the RabbitOS AI assistant for {TWIN_NAME} "
        f"(UUID: {TWIN_UUID}). "
        "You have access to networking, biometric, cryptographic, and "
        "survival tools. Provide accurate, data-driven answers. "
        "When tools are available, use them to get real data."
    )

    def __init__(self, prefer: str = ""):
        """
        prefer: force a specific provider ("ollama", "groq", "gemini", "hf", "anthropic")
        Leave empty for auto-detect.
        """
        self._ollama    = OllamaProvider()
        self._groq      = GroqProvider()
        self._gemini    = GeminiProvider()
        self._hf        = HuggingFaceProvider()
        self._anthropic = AnthropicProvider()
        self._prefer    = prefer
        self._active_provider: Optional[Any] = None
        self._active_name: str = ""
        self._lock      = threading.Lock()
        self._call_count = 0
        self._total_tokens = 0
        self._detect()

    def _detect(self):
        """Detect the best available provider."""
        order = [self._ollama, self._groq, self._gemini,
                 self._hf, self._anthropic]
        if self._prefer:
            name_map = {
                "ollama": self._ollama, "groq": self._groq,
                "gemini": self._gemini, "hf": self._hf,
                "huggingface": self._hf, "anthropic": self._anthropic,
            }
            forced = name_map.get(self._prefer.lower())
            if forced:
                order = [forced] + [p for p in order if p is not forced]

        for provider in order:
            try:
                if hasattr(provider, "detect"):
                    result = provider.detect()
                    # Ollama.detect() returns (bool, model_str)
                    if isinstance(result, tuple):
                        ok, model = result
                        if ok:
                            provider._model = model
                            self._active_provider = provider
                            self._active_name     = provider.NAME
                            _log(f"Provider: {provider.NAME}  model={model}")
                            return
                    elif result:
                        self._active_provider = provider
                        self._active_name     = provider.NAME
                        _log(f"Provider: {provider.NAME}")
                        return
            except Exception:
                pass

        _log("WARNING: No LLM provider available. "
             "Install Ollama or set GROQ_API_KEY / GEMINI_API_KEY.")

    def provider_name(self) -> str:
        return self._active_name or "none"

    def is_ready(self) -> bool:
        return self._active_provider is not None

    def chat(self, messages: List[Dict], tools: List[Dict] = None,
             system: str = "", model: str = "") -> LLMResponse:
        """Single call to the active provider."""
        if not self._active_provider:
            self._detect()
        if not self._active_provider:
            return LLMResponse(
                error="No LLM provider available. "
                      "Run Ollama or set GROQ_API_KEY / GEMINI_API_KEY.",
                provider="none")

        system = system or self.SYSTEM
        try:
            resp = self._active_provider.chat(
                messages, tools=tools, system=system, model=model)
        except Exception as e:
            resp = LLMResponse(error=str(e)[:200], provider=self._active_name)

        # If primary fails, try next provider
        if not resp.ok() and self._prefer == "":
            _log(f"Primary {self._active_name} failed ({resp.error[:60]}), trying fallback...")
            self._fallback(resp.provider)
            if self._active_provider:
                try:
                    resp = self._active_provider.chat(
                        messages, tools=tools, system=system, model=model)
                except Exception as e:
                    resp = LLMResponse(error=str(e)[:200], provider=self._active_name)

        with self._lock:
            self._call_count   += 1
            self._total_tokens += resp.tokens_in + resp.tokens_out

        if resp.ok():
            _log(f"{resp.provider} ({resp.model})  "
                 f"in={resp.tokens_in} out={resp.tokens_out} tok  "
                 f"{resp.latency_ms}ms  "
                 f"tools={len(resp.tool_calls)}")
        else:
            _log(f"ERROR ({resp.provider}): {resp.error[:80]}")

        return resp

    def _fallback(self, failed_provider: str):
        """Switch to next available provider after failure."""
        order = [self._ollama, self._groq, self._gemini,
                 self._hf, self._anthropic]
        for provider in order:
            if provider.NAME == failed_provider:
                continue
            try:
                result = provider.detect()
                if isinstance(result, tuple):
                    ok, model = result
                    if ok:
                        provider._model = model
                        self._active_provider = provider
                        self._active_name     = provider.NAME
                        _log(f"Fallback to: {provider.NAME}")
                        return
                elif result:
                    self._active_provider = provider
                    self._active_name     = provider.NAME
                    _log(f"Fallback to: {provider.NAME}")
                    return
            except Exception:
                pass
        self._active_provider = None
        self._active_name     = ""

    def agentic_loop(self, question: str, tools: List[Dict],
                     tool_dispatcher, system: str = "",
                     max_rounds: int = 10) -> str:
        """
        Full agentic tool-use loop.
        Calls tool_dispatcher(tool_name, tool_input) → str for each tool call.
        Returns final text answer.

        Compatible with rabbit_nettools.BrowserAssistant tool format.
        """
        if not self.is_ready():
            return (f"[LLM not ready — no provider available. "
                    f"Install Ollama: https://ollama.com  "
                    f"or set GROQ_API_KEY at console.groq.com (free)]")

        messages = [{"role": "user", "content": question}]
        system   = system or self.SYSTEM

        for round_n in range(max_rounds):
            resp = self.chat(messages, tools=tools, system=system)

            if not resp.ok():
                return f"[LLM Error] {resp.error}"

            if not resp.has_tools():
                # Final answer
                return resp.text.strip() or "[No response]"

            # Build assistant content block (Anthropic-style for compatibility)
            asst_content = []
            if resp.text:
                asst_content.append({"type": "text", "text": resp.text})
            for tc in resp.tool_calls:
                asst_content.append({
                    "type":  "tool_use",
                    "id":    tc["id"],
                    "name":  tc["name"],
                    "input": tc["input"],
                })
            messages.append({"role": "assistant", "content": asst_content})

            # Execute tools and build result message
            tool_results = []
            for tc in resp.tool_calls:
                _log(f"Tool call: {tc['name']}  input={str(tc['input'])[:60]}")
                try:
                    result = tool_dispatcher(tc["name"], tc["input"])
                    if not isinstance(result, str):
                        result = json.dumps(result, default=str)
                except Exception as e:
                    result = json.dumps({"error": str(e)[:100]})
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": tc["id"],
                    "content":     result[:4000],
                })
            messages.append({"role": "user", "content": tool_results})

        return "[Max rounds reached]"

    def simple_ask(self, question: str, context: str = "") -> str:
        """Quick single-shot question with no tools."""
        content = question
        if context:
            content = f"Context:\n{context}\n\nQuestion: {question}"
        resp = self.chat([{"role": "user", "content": content}])
        return resp.text if resp.ok() else f"[Error: {resp.error}]"

    def status(self) -> Dict:
        return {
            "provider":     self._active_name,
            "ready":        self.is_ready(),
            "calls":        self._call_count,
            "total_tokens": self._total_tokens,
            "ollama_models": self._ollama.list_models(),
            "groq_key":     bool(self._groq._key),
            "gemini_key":   bool(self._gemini._key),
            "hf_token":     bool(self._hf._token),
            "anthropic_key":bool(self._anthropic._key),
            "ts":           datetime.now(timezone.utc).isoformat(),
        }


# ──────────────────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────────────────
_bridge:      Optional[LLMBridge] = None
_bridge_lock  = threading.Lock()

def get_llm(prefer: str = "") -> LLMBridge:
    global _bridge
    with _bridge_lock:
        if _bridge is None:
            _bridge = LLMBridge(prefer)
    return _bridge


# ──────────────────────────────────────────────────────────────────────────────
# Tool definitions (for rabbit_agent.py)
# ──────────────────────────────────────────────────────────────────────────────
LLM_BRIDGE_TOOLS = [
    {
        "name": "llm_status",
        "description": "Get LLM bridge status: active provider, available models, total calls, token counts.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "llm_ask",
        "description": "Ask any question to the active LLM (Ollama/Groq/Gemini/etc). No API key required if Ollama is running.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "context":  {"type": "string", "description": "Optional context/background"},
            },
            "required": ["question"],
        },
    },
    {
        "name": "llm_switch_provider",
        "description": "Switch to a different LLM provider: ollama | groq | gemini | hf | anthropic",
        "input_schema": {
            "type": "object",
            "properties": {
                "provider": {"type": "string",
                             "enum": ["ollama", "groq", "gemini", "hf", "anthropic"]},
            },
            "required": ["provider"],
        },
    },
    {
        "name": "llm_pull_model",
        "description": "Pull/download an Ollama model (e.g. llama3.2, mistral, phi3, gemma2). Free, runs locally.",
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string",
                          "description": "e.g. llama3.2, mistral, phi3, gemma2, qwen2.5"},
            },
            "required": ["model"],
        },
    },
    {
        "name": "llm_list_models",
        "description": "List all locally available Ollama models.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


def dispatch_llm_tool(name: str, inputs: Dict) -> Dict:
    llm = get_llm()
    if name == "llm_status":
        return llm.status()
    elif name == "llm_ask":
        answer = llm.simple_ask(inputs["question"], inputs.get("context", ""))
        return {"answer": answer, "provider": llm.provider_name()}
    elif name == "llm_switch_provider":
        global _bridge
        with _bridge_lock:
            _bridge = LLMBridge(prefer=inputs["provider"])
        return {"provider": _bridge.provider_name(), "ready": _bridge.is_ready()}
    elif name == "llm_pull_model":
        ok = llm._ollama.pull_model(inputs["model"])
        return {"model": inputs["model"], "pulled": ok,
                "models": llm._ollama.list_models()}
    elif name == "llm_list_models":
        return {"models": llm._ollama.list_models(), "provider": llm.provider_name()}
    else:
        return {"error": f"unknown tool: {name}"}


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse, pprint

    p = argparse.ArgumentParser(
        description="RabbitOS LLM Bridge — free multi-provider AI")
    p.add_argument("--status",   action="store_true", help="Show provider status")
    p.add_argument("--ask",      metavar="QUESTION",  help="Ask a question")
    p.add_argument("--provider", metavar="NAME",
                   help="Force provider: ollama|groq|gemini|hf|anthropic")
    p.add_argument("--pull",     metavar="MODEL",     help="Pull Ollama model")
    p.add_argument("--models",   action="store_true", help="List Ollama models")
    args = p.parse_args()

    llm = get_llm(args.provider or "")

    if args.pull:
        llm._ollama.pull_model(args.pull)
    elif args.models:
        models = llm._ollama.list_models()
        if models:
            print("Available Ollama models:")
            for m in models:
                print(f"  {m}")
        else:
            print("Ollama not running or no models installed.")
    elif args.ask:
        print(f"\nProvider: {llm.provider_name()}")
        print("─" * 50)
        answer = llm.simple_ask(args.ask)
        print(answer)
    else:
        pprint.pprint(llm.status())
