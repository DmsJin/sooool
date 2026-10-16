"""Explicitly budgeted Ultrafast Responses calls, ported from olympic_research.

Credentials stay in their owning files. Logs contain only experiment inputs,
model answers, timing, token counts, and non-identifying quota percentages.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
import fcntl
import json
import math
import os
from pathlib import Path
import time
import uuid

import httpx


MODEL = "gpt-6.1-sol"
SERVICE_TIER = "ultrafast"
# https://developers.openai.com/api/docs/pricing (2026-10-15), <=272K input.
PRICES_PER_MILLION = {"input": 12.0, "cached": 0.6, "cache_write": 15.0, "output": 60.0}
DEFAULT_INSTRUCTIONS = (
    "Answer the supplied task using only its text and images. You have no tools. "
    "Return only the requested JSON, without Markdown or explanation."
)


def _write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


class ApiBudget:
    """One append-only ledger, shared by all workers through an OS file lock.

    An unresolved reservation remains charged at its maximum across restarts.
    Store the ledger outside candidate-writable directories and never delete it
    to restart a campaign. Amounts are integer nano-dollars to avoid rounding.
    """

    def __init__(self, path: Path, limit_usd=20.0):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.limit = math.floor(float(limit_usd) * 1_000_000_000)
        if self.limit <= 0:
            raise ValueError("API budget must be positive")
        with self._locked() as (stream, events):
            if not events:
                self._append(stream, {"event": "budget", "limit_nano_usd": self.limit})
            elif events[0] != {"event": "budget", "limit_nano_usd": self.limit}:
                raise ValueError("Existing API ledger has a different budget ceiling")

    @contextmanager
    def _locked(self):
        with self.path.open("a+", encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            # A malformed/truncated record fails closed: never reset accounting.
            events = [json.loads(line) for line in stream if line.strip()]
            yield stream, events

    @staticmethod
    def _append(stream, value):
        stream.seek(0, os.SEEK_END)
        stream.write(json.dumps(value, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())

    @staticmethod
    def _amounts(events):
        amounts = {}
        settled = set()
        for event in events[1:]:
            if event["event"] == "reserve":
                amounts[event["id"]] = event["nano_usd"]
            elif event["event"] == "settle":
                amounts[event["id"]] = event["nano_usd"]
                settled.add(event["id"])
        return amounts, settled

    def reserve(self, input_tokens, max_output_tokens, label="request", *,
                scope="campaign", scope_limit_usd=None):
        if type(input_tokens) is not int or not 0 <= input_tokens <= 272_000:
            raise ValueError("Input token count exceeds the supported pricing range")
        if type(max_output_tokens) is not int or max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        # Every input token could be a cache write, the highest input price.
        maximum = input_tokens * 15_000 + max_output_tokens * 60_000
        with self._locked() as (stream, events):
            amounts, _ = self._amounts(events)
            if any(event.get("overrun") for event in events):
                raise RuntimeError("API campaign stopped because usage exceeded a reservation")
            if sum(amounts.values()) + maximum > self.limit:
                raise RuntimeError("API budget exhausted after accounting for in-flight requests")
            if scope_limit_usd is not None:
                scope_ids = {event["id"] for event in events[1:]
                             if event["event"] == "reserve" and event["scope"] == scope}
                scope_limit = math.floor(float(scope_limit_usd) * 1_000_000_000)
                if sum(amounts[key] for key in scope_ids) + maximum > scope_limit:
                    raise RuntimeError(f"API {scope} budget exhausted after in-flight reservations")
            identifier = uuid.uuid4().hex
            self._append(stream, {"event": "reserve", "id": identifier,
                                  "nano_usd": maximum, "label": str(label), "scope": scope,
                                  "input_tokens_bound": input_tokens,
                                  "output_tokens_bound": max_output_tokens})
        return identifier

    def settle(self, identifier, usage):
        actual = usage_cost_nano(usage)
        with self._locked() as (stream, events):
            amounts, settled = self._amounts(events)
            reserved = amounts[identifier]
            if identifier in settled:
                raise ValueError("API reservation was already settled")
            self._append(stream, {"event": "settle", "id": identifier,
                                  "nano_usd": actual, "usage": usage, "overrun": actual > reserved})
            if actual > reserved:
                raise RuntimeError("API usage exceeded the preflight reservation; stop the campaign")
        return actual / 1_000_000_000

    def snapshot(self):
        with self._locked() as (_, events):
            amounts, settled = self._amounts(events)
        return {"limit_usd": self.limit / 1_000_000_000,
                "committed_usd": sum(amounts.values()) / 1_000_000_000,
                "settled_usd": sum(amounts[k] for k in settled) / 1_000_000_000,
                "unresolved_requests": len(amounts) - len(settled),
                "requests": len(amounts)}


def normalize_api_usage(usage):
    details = usage["input_tokens_details"]
    result = {"input_tokens": usage["input_tokens"],
              "cached_tokens": details["cached_tokens"],
              "cache_write_tokens": details["cache_write_tokens"],
              "output_tokens": usage["output_tokens"],
              "reasoning_tokens": usage["output_tokens_details"]["reasoning_tokens"]}
    if any(type(value) is not int or value < 0 for value in result.values()):
        raise ValueError("Invalid API token usage")
    if result["cached_tokens"] + result["cache_write_tokens"] > result["input_tokens"]:
        raise ValueError("API cached and cache-write tokens exceed input tokens")
    return result


def usage_cost_nano(usage):
    uncached = usage["input_tokens"] - usage["cached_tokens"] - usage["cache_write_tokens"]
    return (uncached * 12_000 + usage["cached_tokens"] * 600
            + usage["cache_write_tokens"] * 15_000 + usage["output_tokens"] * 60_000)


class ApiClient:
    def __init__(self, config: dict, output: Path, budget: ApiBudget, schema: dict | None = None):
        self.config = config
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.budget = budget
        self.schema = schema
        self.instructions = (Path(config["system_instructions_file"]).read_text()
                             if config.get("system_instructions_file") else DEFAULT_INSTRUCTIONS)
        self.max_output_tokens = int(config.get("max_output_tokens", 1024))
        key = Path(config["api_key_file"]).read_text().strip()
        if not key or "\n" in key:
            raise ValueError("API key file must contain one nonempty value")
        self.client = httpx.Client(
            base_url="https://api.openai.com/v1/", timeout=float(config.get("timeout_seconds", 120)),
            headers={"Authorization": "Bearer " + key}, trust_env=False,
        )

    def _payload(self, prompt, images):
        content = [{"type": "input_text", "text": prompt}]
        for path in images:
            data = Path(path).read_bytes()
            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("API observation images must be PNG files")
            content.append({"type": "input_image", "detail": "high",
                            "image_url": "data:image/png;base64," + base64.b64encode(data).decode("ascii")})
        payload = {"model": MODEL, "instructions": self.instructions,
                   "input": [{"role": "user", "content": content}],
                   "reasoning": {"effort": "low"}, "service_tier": SERVICE_TIER,
                   "max_output_tokens": self.max_output_tokens, "store": False,
                   "stream": True, "tools": [], "tool_choice": "none", "truncation": "disabled"}
        if self.schema is not None:
            payload["text"] = {"format": {"type": "json_schema", "name": "decision",
                                          "strict": True, "schema": self.schema}}
        return payload

    def complete(self, prompt: str, images: list[Path | str], out_dir: Path, *, cancel_check=None):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        payload = self._payload(prompt, images)
        _write_json(out_dir / "input.json", {"prompt": prompt, "images": [str(p) for p in images],
                                            "model": MODEL, "effort": "low", "service_tier": SERVICE_TIER,
                                            "max_output_tokens": self.max_output_tokens})
        # The count endpoint covers actual images and schema; it avoids guessed
        # chars/token or model-specific vision constants. Its RTT is measured.
        count_payload = {key: payload[key] for key in ("model", "instructions", "input", "tools")}
        if "text" in payload:
            count_payload["text"] = payload["text"]
        prepare_seconds = time.perf_counter() - started
        counting_started = time.perf_counter()
        response = self.client.post("responses/input_tokens", json=count_payload)
        input_count_seconds = time.perf_counter() - counting_started
        if response.status_code != 200:
            raise RuntimeError(f"API token preflight failed with HTTP {response.status_code}")
        input_tokens = response.json()["input_tokens"]
        # Small protocol-framing headroom is reserved in addition to the count.
        if type(input_tokens) is not int or input_tokens < 0:
            raise ValueError("API token preflight returned an invalid count")
        reason = cancel_check() if cancel_check is not None else None
        if reason is not None:
            result = {"cancelled_before_start": reason, "stage": "after_token_count_before_reservation",
                      "provider_generation_started": False, "wall_seconds": time.perf_counter() - started,
                      "prepare_wall_seconds": prepare_seconds, "input_count_wall_seconds": input_count_seconds}
            _write_json(out_dir / "cancelled_before_start.json", result)
            return result
        # Final admission boundary: reserve and send follow directly. As with
        # any send, scheduling can cross the deadline after admission; already
        # admitted requests retain the existing terminal/uncertain accounting.
        reservation = self.budget.reserve(
            input_tokens + 1024, self.max_output_tokens, out_dir.name,
            scope=self.config.get("budget_scope", "campaign"),
            scope_limit_usd=self.config.get("budget_scope_limit_usd"),
        )
        preflight_seconds = time.perf_counter() - started
        terminal = None
        first_token_seconds = None
        status = "unknown"
        requesting_started = time.perf_counter()
        try:
            with self.client.stream("POST", "responses", json=payload) as stream:
                if stream.status_code != 200:
                    raise RuntimeError(f"Responses API failed with HTTP {stream.status_code}")
                with (out_dir / "timing_events.jsonl").open("w") as events:
                    for line in stream.iter_lines():
                        if time.perf_counter() - started > float(self.config.get("timeout_seconds", 120)):
                            raise TimeoutError("Responses request exceeded the total timeout")
                        if not line.startswith("data: ") or line == "data: [DONE]":
                            continue
                        event = json.loads(line[6:])
                        kind = event["type"]
                        elapsed = time.perf_counter() - started
                        events.write(json.dumps({"type": kind, "wall_seconds": elapsed}) + "\n")
                        if kind == "response.output_text.delta" and first_token_seconds is None:
                            first_token_seconds = elapsed
                        if kind in {"response.completed", "response.incomplete", "response.failed"}:
                            terminal = event["response"]
                            break
                        if kind == "error":
                            raise RuntimeError("Responses API emitted an error event")
            if terminal is None:
                raise RuntimeError("Responses stream ended without a terminal response")
            status = terminal["status"]
            served_model = terminal["model"]
            if served_model != MODEL and not served_model.startswith(MODEL + "-"):
                raise RuntimeError("Responses API served a different model")
            if terminal.get("service_tier") != SERVICE_TIER:
                raise RuntimeError("Responses API did not serve the requested Ultrafast tier")
            if terminal.get("reasoning", {}).get("effort") != "low":
                raise RuntimeError("Responses API did not confirm low reasoning effort")
            usage = normalize_api_usage(terminal["usage"])
            cost = self.budget.settle(reservation, usage)
            if status != "completed":
                raise RuntimeError(f"Responses API terminal status was {status}")
            text = "".join(part["text"] for item in terminal["output"] if item["type"] == "message"
                           for part in item["content"] if part["type"] == "output_text")
            if not text:
                raise RuntimeError("Responses API returned no answer text")
            result = {"text": text, "wall_seconds": time.perf_counter() - started,
                      "first_token_seconds": first_token_seconds, "preflight_seconds": preflight_seconds,
                      "prepare_wall_seconds": prepare_seconds, "input_count_wall_seconds": input_count_seconds,
                      "request_wall_seconds": time.perf_counter() - requesting_started,
                      "usage": usage, "cost_usd": cost, "model": served_model,
                      "effort": "low", "service_tier": terminal["service_tier"], "provider": "api"}
            _write_json(out_dir / "result.json", result)
            return result
        finally:
            _write_json(out_dir / "accounting.json", {"reservation": reservation, "status": status,
                                                       "wall_seconds": time.perf_counter() - started,
                                                       "budget": self.budget.snapshot()})

    def close(self):
        self.client.close()
