#!/usr/bin/env python3
"""
GMR-01 session constitution — the policy layer that evaluates session
demands and computes counterweights.

A 'demand' is a session-submitted task containing proprietary
improvements/modifications. The network 'deems it uneven' when its
modification weight exceeds constitutional tolerances; counterweights
then expand/restrict the session's effective quota.

constitution.json is the editable policy. Evaluation is deterministic
per (demand, constitution_version) so verdicts are reproducible.
"""

import hashlib
import json

CONSTITUTION_PATH = "constitution.json"

DEFAULT_CONSTITUTION = {
    "version": 1,
    "tolerances": {
        "max_modification_weight": 10.0,
        "protected_modules": ["bus", "kernel", "sessions", "constitution"],
        "max_demands_per_session": 64,
        "quota_budget_cap": 100.0,
    },
    "counterweight_rules": {
        "uneven_demand": {"quota_delta": -5.0, "attention_boost": 0.0},
        "protected_module_touch": {"quota_delta": -25.0,
                                   "attention_boost": 2.0},
        "over_demand_cap": {"quota_delta": -50.0, "attention_boost": 0.0},
    },
}


def load_constitution(path=CONSTITUTION_PATH):
    try:
        with open(path) as f:
            c = json.load(f)
        c.setdefault("tolerances", DEFAULT_CONSTITUTION["tolerances"])
        c.setdefault("counterweight_rules",
                     DEFAULT_CONSTITUTION["counterweight_rules"])
        return c
    except FileNotFoundError:
        return dict(DEFAULT_CONSTITUTION)


def _mod_weight(mod):
    """Deterministic pseudo-weight of one modification descriptor."""
    s = json.dumps(mod, sort_keys=True, default=str)
    return (int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)
            % 1000) / 100.0


def evaluate(demand, constitution=None, demand_count=0):
    """Score a demand against the constitution.

    Returns {admissible, uneven, flags, counterweights, weight}.
    counterweights = {"quota_delta", "attention_boost"} — applied to the
    session's finalized quota project.
    """
    c = constitution or load_constitution()
    tol = c["tolerances"]
    rules = c["counterweight_rules"]

    mods = demand.get("modifications", []) or []
    weight = round(sum(_mod_weight(m) for m in mods), 4)

    flags = []
    quota_delta = 0.0
    attention_boost = 0.0

    # network deems uneven: modification weight over tolerance
    uneven = weight > tol["max_modification_weight"]
    if uneven:
        flags.append("uneven_weight")
        r = rules["uneven_demand"]
        quota_delta += r["quota_delta"]
        attention_boost += r["attention_boost"]

    # touches a protected module?
    touched = {m.get("module") for m in mods if isinstance(m, dict)}
    hit = touched & set(tol["protected_modules"])
    if hit:
        flags.append("protected_module_touch")
        r = rules["protected_module_touch"]
        quota_delta += r["quota_delta"]
        attention_boost += r["attention_boost"]

    # session over its demand cap?
    if demand_count >= tol["max_demands_per_session"]:
        flags.append("over_demand_cap")
        r = rules["over_demand_cap"]
        quota_delta += r["quota_delta"]
        attention_boost += r["attention_boost"]

    return {
        "admissible": not flags or "over_demand_cap" not in flags,
        "uneven": uneven,
        "flags": flags,
        "protected_hit": sorted(hit),
        "weight": weight,
        "counterweights": {
            "quota_delta": quota_delta,
            "attention_boost": attention_boost,
        },
        "constitution_version": c.get("version", 1),
    }


def counterweight_note(verdict):
    cw = verdict["counterweights"]
    return (f"counterweights: quota_delta={cw['quota_delta']:+.1f} "
            f"attention_boost={cw['attention_boost']:+.1f}")
