"""Paid Responses client. Key stays in process memory; no retries or fallback."""
import base64
import hashlib
import json
import math
import re
import struct
import time

from .budget import BudgetLedger, reservation_usd, usage_usd

MODEL = "gpt-6.1-sol"
TIER = "ultrafast"


class ResponseStreamError(RuntimeError):
    """Public transport metadata without provider messages or private content."""
    def __init__(self, message, diagnostics):
        super().__init__(message)
        self.diagnostics = diagnostics


def safe_code(value):
    return value if isinstance(value,str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,200}",value) else None


def png_content(data, detail="high"):
    if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
        raise ValueError("Expected PNG image")
    width, height = struct.unpack(">II", data[16:24])
    if not (0 < width <= 640 and 0 < height <= 480):
        raise ValueError("PNG must fit 640x480 reservation bound")
    return {"type": "input_image", "detail": detail, "image_url": "data:image/png;base64," + base64.b64encode(data).decode("ascii")}


class ApiClient:
    def __init__(self, key, ledger_path, stage="profile", max_output_tokens=128, session=None, detail="high", output_schema=None, preserve_schema_order=False, budget_limits=None):
        if not key:
            raise ValueError("API key required")
        if type(max_output_tokens) is not int or not 16 <= max_output_tokens <= 512:
            raise ValueError("Output cap must be an integer between 16 and 512")
        if session is None:
            import requests
            session = requests.Session()
        if detail not in ("low", "high", "auto"):
            raise ValueError("Invalid image detail")
        self.detail = detail
        self.session = session
        self.key = key
        self.ledger = BudgetLedger(ledger_path, **(budget_limits or {}))
        self.stage = stage
        self.max_output_tokens = max_output_tokens
        if output_schema is not None and not isinstance(output_schema, dict):
            raise ValueError("Output schema must be an object")
        self.schema_text = json.dumps(output_schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False) if output_schema is not None else ""
        if type(preserve_schema_order) is not bool:
            raise ValueError("preserve_schema_order must be boolean")
        self.preserve_schema_order = preserve_schema_order
        encoded = json.dumps(output_schema, separators=(",", ":"), ensure_ascii=False) if preserve_schema_order else self.schema_text
        self.output_schema = json.loads(encoded) if output_schema is not None else None

    def close(self):
        self.session.close()

    def decide(self, prompt, images, validate=None, timing_origin=None, on_legal_action=None):
        if not 1 <= len(images) <= 3:
            raise ValueError("Use 1-3 actual frontend images")
        schema_validator = None
        if on_legal_action is not None:
            if not callable(on_legal_action) or not callable(validate) or self.output_schema is None:
                raise ValueError("Early delivery requires a callback, action validator, and strict output schema")
            # Fail before reservation/network if the local strict validator is unavailable.
            import jsonschema
            jsonschema.Draft202012Validator.check_schema(self.output_schema)
            schema_validator = jsonschema.Draft202012Validator(self.output_schema)
        def strict_json(answer):
            def pairs(items):
                value = {}
                for key,item in items:
                    if key in value:raise ValueError("Duplicate JSON key")
                    value[key] = item
                return value
            def invalid_constant(value):raise ValueError("Nonfinite JSON constant")
            def finite_float(value):
                result=float(value)
                if not math.isfinite(result):raise ValueError("Nonfinite JSON number")
                return result
            return json.loads(answer, object_pairs_hook=pairs, parse_constant=invalid_constant, parse_float=finite_float)
        stage_timing = {"api_prepare_started_wall_s": time.monotonic() - timing_origin} if timing_origin is not None else None
        prep = time.perf_counter()
        content = [{"type": "input_text", "text": prompt}] + [png_content(i, self.detail) for i in images]
        payload = {"model": MODEL, "service_tier": TIER, "reasoning": {"effort": "low"}, "max_output_tokens": self.max_output_tokens,
                   "input": [{"role": "user", "content": content}], "stream": True, "store": False}
        shape = {"model": MODEL, "tier": TIER, "effort": "low", "max_output_tokens": self.max_output_tokens, "detail": self.detail, "image_count": len(images)}
        if self.output_schema is not None:
            payload["text"] = {"format": {"type": "json_schema", "name": "touhou_grounded_plan", "strict": True, "schema": self.output_schema}}
            shape["schema_sha256"] = hashlib.sha256(self.schema_text.encode("utf-8")).hexdigest()
            shape["preserve_schema_order"] = self.preserve_schema_order
        rid = self.ledger.reserve(self.stage, reservation_usd(prompt + self.schema_text, len(images), self.max_output_tokens), shape)
        prepared = time.perf_counter() - prep
        start = time.perf_counter()
        if stage_timing is not None:stage_timing["network_started_wall_s"] = time.monotonic() - timing_origin
        ttft = None
        valid_at = None
        text = ""
        response_obj = None
        terminal = None
        refused = False
        settled = False
        early_answer = None
        early_attempted = False
        callback_error = None
        early_callback_s = None
        event_counts = {}
        provider_error_code = None
        provider_response_id = None
        http_status = None
        provider_request_id = None
        content_type = None
        def failure(message, code):
            diagnostics = {"http_status":http_status,"provider_request_id":provider_request_id,
                "content_type":content_type,
                "provider_response_id":provider_response_id,"terminal_event":terminal,
                "terminal_status":safe_code((response_obj or {}).get("status")),
                "provider_error_code":code,"event_counts":dict(event_counts),
                "incomplete_reason":safe_code(((response_obj or {}).get("incomplete_details") or {}).get("reason")),
                "output_text_chars":len(text),"has_terminal_usage":bool((response_obj or {}).get("usage"))}
            return ResponseStreamError(message+": "+code,diagnostics)
        try:
            with self.session.post("https://api.openai.com/v1/responses", headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"}, json=payload, stream=True, timeout=(15, 120)) as response:
                # Do not log HTTP response bodies: provider errors can include input.
                http_status = response.status_code
                headers = getattr(response,"headers",{})
                provider_request_id = safe_code(headers.get("x-request-id"))
                if response.status_code != 200:
                    raise failure("Responses HTTP status "+str(response.status_code),"http_error")
                media_type = headers.get("Content-Type","").split(";",1)[0].strip().lower()
                content_type = media_type if re.fullmatch(r"[a-z0-9.+-]{1,50}/[a-z0-9.+-]{1,50}",media_type) else None
                if content_type and content_type != "text/event-stream":
                    raise failure("Expected SSE response","unexpected_content_type")
                for raw in response.iter_lines(chunk_size=1):
                    if not raw or not raw.startswith(b"data:"):
                        continue
                    data = raw[5:].strip()
                    if data == b"[DONE]":
                        continue
                    event = json.loads(data)
                    if not isinstance(event,dict):
                        raise failure("Expected SSE event object","invalid_event_object")
                    kind = event.get("type")
                    if safe_code(kind):event_counts[kind] = event_counts.get(kind,0)+1
                    meta = event.get("response")
                    if isinstance(meta,dict):
                        provider_response_id = safe_code(meta.get("id")) or provider_response_id
                        error = meta.get("error")
                        if isinstance(error,dict):provider_error_code = safe_code(error.get("code")) or provider_error_code
                    if kind == "error":
                        error = event.get("error") if isinstance(event.get("error"),dict) else event
                        provider_error_code = safe_code(error.get("code")) or "stream_error"
                    if kind in ("response.refusal.delta", "response.refusal.done"):
                        refused = True
                    if kind == "response.output_text.delta":
                        if ttft is None:
                            ttft = time.perf_counter() - start
                        text += event.get("delta", "")
                        if validate is not None and valid_at is None:
                            try:
                                if validate(text) is not False:
                                    valid_at = time.perf_counter() - start
                            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                                pass
                        if on_legal_action is not None and not early_attempted and not refused:
                            try:
                                candidate = strict_json(text)
                                schema_validator.validate(candidate)
                                action_valid = validate(text) is not False
                            except (ValueError, TypeError, KeyError, jsonschema.ValidationError):
                                action_valid = False
                            if action_valid:
                                early_attempted = True
                                early_answer = text
                                early_ready_ns = time.monotonic_ns()
                                meta = {"request_id": rid, "early_legal": True, "terminal_pending": True,
                                        "legal_action_s": time.perf_counter()-start, "early_legal_ready_ns": early_ready_ns}
                                if timing_origin is not None:
                                    meta["stage_timing"] = {"early_legal_ready_wall_s": time.monotonic()-timing_origin}
                                callback_started=time.perf_counter()
                                try:
                                    on_legal_action({"answer": text, "meta": meta})
                                except Exception as error:
                                    # A consumer failure must not discard terminal billing usage.
                                    callback_error = error
                                finally:
                                    early_callback_s=time.perf_counter()-callback_started
                    if kind in ("response.completed", "response.failed", "response.incomplete"):
                        if not isinstance(event.get("response"),dict):
                            raise failure("Expected terminal response object","invalid_terminal_response")
                        response_obj = event["response"]
                        terminal = kind
                elapsed = time.perf_counter() - start
                if stage_timing is not None:stage_timing["network_completed_wall_s"] = time.monotonic() - timing_origin
            if not response_obj or not response_obj.get("usage"):
                if provider_error_code:
                    raise failure("API reported failure without terminal usage",provider_error_code)
                if terminal == "response.failed":
                    raise failure("API response failed without terminal usage","failed_without_usage")
                if terminal is None:
                    raise failure("Stream ended without a terminal event","missing_terminal_event")
                raise failure("Terminal response usage missing","missing_terminal_usage")
            if response_obj.get("model") != MODEL or response_obj.get("service_tier") != TIER:
                raise RuntimeError("Response model/tier mismatch; reconcile usage manually")
            usage = response_obj["usage"]
            cost = usage_usd(usage)
            # Settle even incomplete responses: output tokens (including reasoning)
            # are billable and included in the reservation.
            settled = True
            self.ledger.settle(rid, cost, usage)
            if stage_timing is not None:stage_timing["usage_settled_wall_s"] = time.monotonic() - timing_origin
            refused = refused or any(content.get("type") == "refusal" for item in response_obj.get("output", []) for content in item.get("content", []))
            if refused:
                raise RuntimeError("Response refused the action request")
            if terminal != "response.completed":
                raise failure("Response ended without completion",provider_error_code or "response_not_completed")
            if provider_error_code:
                raise failure("API reported a stream error",provider_error_code)
            if on_legal_action is not None:
                schema_validator.validate(strict_json(text))
                canonical = ''.join(content.get('text','') for item in response_obj.get('output',[]) for content in item.get('content',[]) if content.get('type')=='output_text')
                if canonical and canonical.strip()!=text.strip():
                    raise RuntimeError("Terminal canonical text differs from streamed action")
                if early_answer is not None and text.strip() != early_answer.strip():
                    raise RuntimeError("Final text differs from the early complete action")
                if callback_error is not None:
                    raise RuntimeError("Early action consumer failed after billing settlement") from callback_error
            valid = True
            if validate is not None:
                try:
                    valid = validate(text) is not False
                except (ValueError, TypeError, KeyError):
                    valid = False
            if on_legal_action is not None and not valid:
                raise RuntimeError("Final action validation failed after early delivery")
            if valid and valid_at is None:
                valid_at = elapsed
            result = {"answer": text, "meta": {"request_id": rid, "provider_response_id": response_obj.get("id"), "ttft_s": ttft, "legal_action_s": valid_at if valid else None, "total_s": elapsed, "prepare_s": prepared, "valid": valid, "usage": usage, "usd": str(cost), "shape": shape}}
            if on_legal_action is not None:
                result["meta"]["early_legal_delivered"] = early_answer is not None and callback_error is None
                result["meta"]["early_callback_s"] = early_callback_s
            if stage_timing is not None:result["meta"]["stage_timing"] = stage_timing
            return result
        except Exception as exc:
            if not settled:
                self.ledger.unknown(rid, type(exc).__name__)
            elif on_legal_action is not None:
                self.ledger.block("Early action terminal verification failed: " + type(exc).__name__)
            raise
