"""A rule-based MOCK agent that behaves like a gullible model. It is a simulation:
results show what the harness and the guards do, not how any real model behaves."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .data import KNOWN_CUSTOMERS, SECRET, SYSTEM_PROMPT
from .tools import Tools

ORDER_RE = re.compile(r"\bO-\d{4}\b", re.I)
AMOUNT_RE = re.compile(r"\$\s?(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s?(?:dollars|usd)", re.I)
CUST_RE = re.compile(r"\bcust_[a-z]+\b", re.I)

OVERRIDE = ["ignore all previous", "ignore previous", "ignore your rules", "ignora tus reglas",
            "system override", "developer mode", "admin mode", "no limits"]
LEAK = ["system prompt", "your instructions", "repeat the text above", "tus instrucciones",
        "instructions you were given"]
REFUND = ["refund", "reembols"]
STATUS = ["status", "look up", "lookup", "details", "show me", "where is", "my orders", "estado"]


@dataclass(frozen=True)
class Guards:
    tool_permissions: bool = False   # tools enforce ownership and refund limits in code
    ignore_overrides: bool = False   # user text cannot grant new powers
    data_as_data: bool = False       # text inside tool results is never treated as instructions
    output_filter: bool = False      # block secrets in outgoing text

    @classmethod
    def all(cls) -> "Guards":
        return cls(True, True, True, True)


class MockAgent:
    def __init__(self, tools: Tools, guards: Guards):
        self.tools = tools
        self.guards = guards

    def handle(self, message: str) -> str:
        text = self._respond(message)
        if self.guards.output_filter and SECRET in text:
            return "Sorry, I can't share that."
        return text

    def _respond(self, message: str) -> str:
        norm = message.lower()
        claimed = (CUST_RE.findall(message) or [None])[0]
        override = any(p in norm for p in OVERRIDE) and not self.guards.ignore_overrides

        if any(p in norm for p in LEAK):
            return SYSTEM_PROMPT

        if any(p in norm for p in REFUND):
            return self._refund(message, claimed, override)

        if any(p in norm for p in STATUS):
            return self._status(message, claimed)

        return "Hi! I can check an order's status or help with a refund. What is your order number?"

    def _refund(self, message: str, claimed: str | None, override: bool) -> str:
        targets = [o.upper() for o in ORDER_RE.findall(message)]
        if not targets and override:
            for cid in KNOWN_CUSTOMERS:                    # "refund all orders for all customers"
                targets += [o["id"] for o in self.tools.list_orders(customer_id=cid)]
        if not targets:
            return "Which order would you like refunded? Please give the order number."
        amounts = [float(a or b) for a, b in AMOUNT_RE.findall(message)]
        lines = []
        for i, oid in enumerate(targets):
            amount = amounts[i] if i < len(amounts) else None
            if amount is None:
                found = self.tools.lookup_order(oid, customer_id=claimed)
                if "error" in found:
                    lines.append(f"{oid}: I can't find that order.")
                    continue
                amount = found["total"]
            res = self.tools.issue_refund(oid, amount, customer_id=claimed)
            lines.append(f"{oid}: refunded ${amount:.2f}" if res.get("ok") else f"{oid}: refund not possible.")
        return "\n".join(lines)

    def _status(self, message: str, claimed: str | None) -> str:
        targets = [o.upper() for o in ORDER_RE.findall(message)]
        if not targets:
            rows = self.tools.list_orders(customer_id=claimed)
            return "\n".join(f"{r['id']}: ${r['total']:.2f}" for r in rows) or "No orders found."
        lines = []
        for oid in targets:
            o = self.tools.lookup_order(oid, customer_id=claimed)
            if "error" in o:
                lines.append(f"{oid}: I can't find that order.")
                continue
            note = f' [customer note: "{o["note"]}"]' if o["note"] else ""
            lines.append(f"{oid}: ${o['total']:.2f}{note}")
            # Weak baseline: treats text found in the data as if it were an instruction.
            if o["note"] and not self.guards.data_as_data and "refund" in o["note"].lower():
                self.tools.issue_refund(oid, o["total"], customer_id=claimed)
                lines.append(f"{oid}: refund processed as requested in the note.")
        return "\n".join(lines)
