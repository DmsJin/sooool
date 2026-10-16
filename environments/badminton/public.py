"""Public observation filtering and absolute contact-time conversion."""

_SPEC_KEYS = {
    "sport", "frame", "robot", "base", "court", "racket", "shuttle",
    "arm_limits", "velocity_rule", "cameras", "image", "image_layout", "serve",
    "match", "act", "skill_contract", "timing",
}



_PRIVATE_KEYS = {
    "seed", "episode_seed", "env_seed", "latency_seed", "random_seed", "truth",
    "truth_view", "hidden_state", "qpos", "qvel", "path", "wall_mono",
}



def public_data(value):
    if isinstance(value, dict):
        return {key: public_data(item) for key, item in value.items() if key not in _PRIVATE_KEYS}
    if isinstance(value, list):
        return [public_data(item) for item in value]
    return value



def public_spec(spec: dict) -> dict:
    """Keep the public geometry and physical limits, without private identifiers."""
    out = public_data({key: value for key, value in spec.items() if key in _SPEC_KEYS})
    # Keep request ranges, feasibility and feedback; omit the long testing/implementation prose.
    if "skill_contract" in out:
        keep = {"call", "request", "feasible", "replaces", "notes"}
        out["skill_contract"] = {
            name: {key: value for key, value in contract.items() if key in keep}
            for name, contract in out["skill_contract"].items() if name in {"act", "toss", "move"}
        }
        for contract in out["skill_contract"].values():
            if "feasible" in contract:
                contract["feasible"] = contract["feasible"].split(" Every API-test")[0]
            if "notes" in contract:
                contract["notes"] = {key: value for key, value in contract["notes"].items()
                                     if key in {"stance", "feedback", "contact_law", "timing"}}
    return out



def native_action(action: dict, frame: int) -> dict:
    """Convert the model's absolute contact target at the actual native effect frame."""
    if action['type'] != 'act':
        return dict(action)
    steps = round(action['contact_at_game_time'] * 100) - frame
    if steps <= 0:
        raise ValueError('contact_time_expired')
    if steps > 500:
        raise ValueError('remaining_preparation_exceeds_5_seconds')
    return {**{key: value for key, value in action.items() if key != 'contact_at_game_time'}, 't': steps / 100}



def _unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result
