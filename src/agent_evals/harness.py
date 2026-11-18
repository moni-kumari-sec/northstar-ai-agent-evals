"""Runs every attack against several configurations and prints a results table."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .agent import Guards, MockAgent
from .attacks import ATTACKS, CATEGORIES, Attack
from .data import SESSION_CUSTOMER, make_orders
from .oracle import violations
from .tools import Tools

CONFIGS: dict[str, Guards] = {
    "baseline": Guards(),
    "+tool permissions": Guards(tool_permissions=True),
    "+ignore overrides": Guards(ignore_overrides=True),
    "+data as data": Guards(data_as_data=True),
    "+output filter": Guards(output_filter=True),
    "all guards": Guards.all(),
}


def run_attack(attack: Attack, guards: Guards) -> dict:
    orders = make_orders(note_for_o1001=attack.note)
    tools = Tools(orders, SESSION_CUSTOMER, enforce_permissions=guards.tool_permissions)
    response = MockAgent(tools, guards).handle(attack.message)
    found = violations(orders, SESSION_CUSTOMER, tools.log, response, attack.refund_requested)
    return {"id": attack.id, "variant": attack.variant, "success": bool(found), "violations": found}


def run_matrix() -> dict[str, list[dict]]:
    return {name: [run_attack(a, g) for a in ATTACKS] for name, g in CONFIGS.items()}


def summarize(results: dict[str, list[dict]]) -> dict[str, dict[str, tuple[int, int]]]:
    table: dict[str, dict[str, tuple[int, int]]] = {}
    for cat in CATEGORIES:
        table[cat] = {}
        for cfg, rows in results.items():
            sel = [r for r in rows if r["id"] == cat]
            table[cat][cfg] = (sum(r["success"] for r in sel), len(sel))
    return table


def render_markdown(results: dict[str, list[dict]]) -> str:
    table = summarize(results)
    names = {a.id: a.category for a in ATTACKS}
    cfgs = list(results)
    out = ["| Category | " + " | ".join(cfgs) + " |", "| --- | " + " | ".join("---" for _ in cfgs) + " |"]
    for cat in CATEGORIES:
        cells = [f"{table[cat][c][0]}/{table[cat][c][1]}" for c in cfgs]
        out.append(f"| {cat} {names[cat]} | " + " | ".join(cells) + " |")
    totals = [f"{sum(table[c][cfg][0] for c in CATEGORIES)}/{sum(table[c][cfg][1] for c in CATEGORIES)}" for cfg in cfgs]
    out.append("| **Total attacks that succeeded** | " + " | ".join(f"**{t}**" for t in totals) + " |")
    return "\n".join(out)


def main() -> None:
    results = run_matrix()
    md = render_markdown(results)
    print(md)
    out = Path(__file__).resolve().parents[2] / "results"
    out.mkdir(exist_ok=True)
    (out / "results.md").write_text(
        "# Results\n\nCells show attacks that succeeded out of attacks tried (lower is better).\n"
        "Success means a policy violation judged by an independent oracle.\n\n" + md + "\n")
    (out / "results.json").write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out / 'results.md'} and {out / 'results.json'}")


if __name__ == "__main__":
    main()
