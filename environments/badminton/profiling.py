"""Serial API latency measurement on frozen public camera observations."""
import json
import math
from pathlib import Path
import statistics
import time

from .api import TacticalAPI, realtime_prompt
from .runner import PROFILE_CALLS, _write


def profile_api(source, output, recipe, *, key, budget_usd, ledger_path):
    """Measure exactly 10 calls through the same API transport as live play."""
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    observations = [json.loads(line) for line in (source / "events.jsonl").read_text().splitlines()
                    if json.loads(line)["event"] == "observation"]
    if len(observations) < PROFILE_CALLS:
        raise ValueError(f"Profiling requires at least {PROFILE_CALLS} distinct public observations")
    client = TacticalAPI(key, output, budget_usd, recipe, ledger_path=ledger_path, stage="profile")
    samples = []
    try:
        for number in range(PROFILE_CALLS):
            observation = observations[round(number * (len(observations) - 1) / (PROFILE_CALLS - 1))]
            image = source / "images" / f'frame-{observation["frame"]:07d}.png'
            started = time.monotonic()
            result = client.act(realtime_prompt(observation), image.read_bytes(), observation["spec"],
                                output / "requests" / f"request-{number:05d}", lambda packet: None)
            samples.append({"latency_ms": result["timing"]["json_ready_seconds"] * 1000,
                            "service_ms": result["timing"]["terminal_seconds"] * 1000,
                            "client_total_ms": (time.monotonic() - started) * 1000,
                            "source_frame": observation["frame"], "cost_usd": result["cost_usd"]})
            _write(output / "progress.json", {"requested_calls": PROFILE_CALLS, "terminal_calls": len(samples)})
    finally:
        client.close()
        _write(output / "ledger.json", client.ledger.snapshot())
    latencies = sorted(s["latency_ms"] for s in samples)
    result = {"action_mode": "conditional_tactical_v1", "source": "api", "model": recipe["model"],
              "effort": recipe["effort"], "service_tier": recipe["service_tier"], "workers": 1, "capacity": 1,
              "samples": samples, "requested_calls": PROFILE_CALLS, "terminal_calls": len(samples),
              "usable_for_simulation": True,
              "summary": {"unit": "ms", "count": len(samples), "mean": statistics.fmean(latencies),
                          "p95": latencies[math.ceil(.95 * len(latencies)) - 1], "max": max(latencies)},
              "measurement": "same_transport_as_realtime_complete_valid_JSON_and_terminal_service_time",
              "purpose": "tactical_api_latency_profile", "source_episode": str(source)}
    _write(output / "profile.json", result)
    return result
