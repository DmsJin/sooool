"""Stream one paid tactical answer and settle every terminal response."""
import base64
import copy
from decimal import Decimal
import json
import math
from pathlib import Path
import struct
import time

import requests

from environments.touhou.research.budget import BudgetLedger, usage_usd
from .public import _unique_object
from .tactics import POLICY_ROOT, SCHEMA, decode_intent, format_prompt

REALTIME_SCHEMA = copy.deepcopy(SCHEMA)
REALTIME_SCHEMA["properties"]["brief"] = {"type": "string", "minLength": 1, "maxLength": 60}
REALTIME_SCHEMA["required"].append("brief")
BRIEF_INSTRUCTION = (
    '\nFor this realtime run, also return "brief": one short English public decision summary, '
    'about 6-10 words and at most 60 characters. Describe the visible situation and your chosen '
    'tactics in this response. Keep memory short. Include brief with the conditional strategy JSON.\n'
)


def decode_response(text, spec):
    """Validate the public summary and the unchanged tactical intent together."""
    packet = json.loads(text, object_pairs_hook=_unique_object)
    if not isinstance(packet, dict) or set(packet) != set(REALTIME_SCHEMA["required"]):
        raise ValueError("Realtime answer requires the conditional strategy and brief")
    brief = packet["brief"]
    if not isinstance(brief, str) or not brief.strip() or len(brief) > 60 or "\n" in brief:
        raise ValueError("Expected a single-line English public summary of 1-60 characters")
    intent = decode_intent(json.dumps({k: v for k, v in packet.items() if k != "brief"}), spec)
    return {"intent": intent, "brief": brief}


def realtime_prompt(snapshot):
    return format_prompt(snapshot).replace(
        "Return exactly normal,under_pressure,opponent_back,recovery,horizon_game_s,memory as JSON.",
        "Return normal,under_pressure,opponent_back,recovery,horizon_game_s,memory,brief as JSON.") + BRIEF_INSTRUCTION


class TacticalAPI:
    """Own a serial HTTP session, usage accounting and early complete-JSON delivery."""

    def __init__(self, key, output, budget_usd, recipe):
        self.key, self.recipe = key, recipe
        self.session = requests.Session()
        limits = {"total_limit": budget_usd, "admission_limit": budget_usd,
                  "stage_caps": {k: budget_usd for k in ("profile", "reprofile", "realtime")}}
        self.ledger = BudgetLedger(Path(output) / "ledger.json", **limits)
        self.system = (POLICY_ROOT / "system.txt").read_text()

    def act(self, prompt, image, spec, directory, publish):
        directory = Path(directory)
        directory.mkdir(parents=True)
        (directory / "prompt.txt").write_text(prompt)
        (directory / "image.png").write_bytes(image)
        width, height = struct.unpack(">II", image[16:24])
        if image[:8] != b"\x89PNG\r\n\x1a\n" or (width, height) != (1920, 720):
            raise ValueError("Expected the native 1920x720 public camera sheet")
        # At high detail, reserve 8192 tokens per 640x480 region, including resizing overhead.
        image_bound = math.ceil(width / 640) * math.ceil(height / 480) * 8192
        text_bound = len((self.system + prompt + json.dumps(REALTIME_SCHEMA)).encode())
        cap = self.recipe["max_output_tokens"]
        reservation = (Decimal(text_bound + image_bound + 512) * 15 + Decimal(cap) * 60) / 1000000
        rid = self.ledger.reserve("realtime", reservation, {"model": self.recipe["model"],
                                                         "service_tier": self.recipe["service_tier"]})
        payload = {"model": self.recipe["model"], "service_tier": self.recipe["service_tier"],
                   "reasoning": {"effort": self.recipe["effort"]}, "instructions": self.system,
                   "stream": True, "store": False, "max_output_tokens": cap,
                   "text": {"format": {"type": "json_schema", "name": "badminton_tactics",
                                       "strict": True, "schema": REALTIME_SCHEMA}},
                   "input": [{"role": "user", "content": [
                       {"type": "input_text", "text": prompt},
                       {"type": "input_image", "detail": "high", "image_url":
                        "data:image/png;base64," + base64.b64encode(image).decode()}]}]}
        start = time.monotonic()
        timing = {"sent_monotonic": start, "ttft_seconds": None, "json_ready_seconds": None}
        answer, response, published = "", None, None
        settled, identity = False, False
        try:
            with (directory / "events.jsonl").open("w", buffering=1) as event_log, self.session.post("https://api.openai.com/v1/responses", json=payload,
                    headers={"Authorization": "Bearer " + self.key}, stream=True, timeout=(15, 120)) as stream:
                stream.raise_for_status()
                for raw in stream.iter_lines(chunk_size=1):
                    if not raw.startswith(b"data:") or raw[5:].strip() == b"[DONE]":
                        continue
                    event = json.loads(raw[5:])
                    event_log.write(json.dumps(event, separators=(",", ":")) + "\n")
                    kind = event["type"]
                    if kind == "response.created":
                        created = event["response"]
                        identity = (created["model"] == self.recipe["model"]
                                    and created["service_tier"] == self.recipe["service_tier"])
                        if not identity:
                            raise RuntimeError("API model/tier differs from the realtime recipe")
                    elif kind == "response.output_text.delta":
                        now = time.monotonic()
                        if timing["ttft_seconds"] is None:
                            timing["ttft_seconds"] = now - start
                        answer += event["delta"]
                        if published is None and identity:
                            try:
                                packet = decode_response(answer, spec)
                            except (ValueError, TypeError):
                                continue
                            timing.update(json_ready_seconds=now - start, json_ready_monotonic=now)
                            published = answer
                            publish({**packet, **timing})
                    elif kind in {"response.completed", "response.failed", "response.incomplete"}:
                        response = event["response"]
                        (directory / "response.json").write_text(json.dumps(response, indent=2) + "\n")
                        timing["terminal_seconds"] = time.monotonic() - start
                timing["stream_end_seconds"] = time.monotonic() - start
            if response is not None and response["status"] == "failed":
                error = response["error"]
                raise RuntimeError(f'API response failed: {error["code"]}: {error["message"]}')
            if response is None or response.get("usage") is None:
                raise RuntimeError("API terminal usage missing")
            cost = usage_usd(response["usage"])
            self.ledger.settle(rid, cost, response["usage"])
            settled = True
            canonical = "".join(c["text"] for item in response["output"] for c in item.get("content", [])
                                if c["type"] == "output_text")
            if (response["status"] != "completed" or response["model"] != self.recipe["model"]
                    or response["service_tier"] != self.recipe["service_tier"]
                    or published is None or canonical.strip() != published.strip() or answer.strip() != published.strip()):
                self.ledger.block("Published tactical response failed terminal verification")
                raise RuntimeError("API terminal answer differs from the published tactical answer")
            result = {"answer": answer, "timing": timing, "usage": response["usage"], "cost_usd": str(cost),
                      "ledger_request_id": rid,
                      "model": response["model"], "service_tier": response["service_tier"],
                      "response_id": response["id"]}
            (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            return result
        except BaseException as exc:
            if not settled:
                self.ledger.unknown(rid, type(exc).__name__)
            (directory / "error.json").write_text(json.dumps({"error_type": type(exc).__name__, "timing": timing}))
            raise

    def close(self):
        self.session.close()
        self.key = None
