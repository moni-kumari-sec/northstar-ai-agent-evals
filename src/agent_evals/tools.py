"""Tools the agent can call. With enforce_permissions=False they trust whatever the
model passes in (the weak baseline). With True they enforce the rules in code."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .data import REFUND_LIMIT, Order


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    result: Any


@dataclass
class Tools:
    orders: dict[str, Order]
    session_customer: str
    enforce_permissions: bool = False
    log: list[ToolCall] = field(default_factory=list)
    refunds: list[tuple[str, float]] = field(default_factory=list)

    def _record(self, name: str, args: dict, result: Any) -> Any:
        self.log.append(ToolCall(name, args, result))
        return result

    @staticmethod
    def _view(o: Order) -> dict:
        return {"id": o.id, "customer_id": o.customer_id, "total": o.total, "note": o.note}

    def lookup_order(self, order_id: str, customer_id: str | None = None) -> dict:
        args = {"order_id": order_id, "customer_id": customer_id}
        order = self.orders.get(order_id)
        if order is None:
            return self._record("lookup_order", args, {"error": "not_found"})
        if self.enforce_permissions and order.customer_id != self.session_customer:
            return self._record("lookup_order", args, {"error": "not_found"})
        return self._record("lookup_order", args, self._view(order))

    def list_orders(self, customer_id: str | None = None) -> list[dict]:
        args = {"customer_id": customer_id}
        cid = self.session_customer if self.enforce_permissions else (customer_id or self.session_customer)
        result = [self._view(o) for o in self.orders.values() if o.customer_id == cid]
        return self._record("list_orders", args, result)

    def issue_refund(self, order_id: str, amount: float, customer_id: str | None = None) -> dict:
        args = {"order_id": order_id, "amount": amount, "customer_id": customer_id}
        order = self.orders.get(order_id)
        if order is None:
            return self._record("issue_refund", args, {"error": "not_found"})
        if self.enforce_permissions:
            if order.customer_id != self.session_customer:
                return self._record("issue_refund", args, {"error": "not_found"})
            if amount <= 0 or amount > min(order.total, REFUND_LIMIT):
                return self._record("issue_refund", args, {"error": "amount_not_allowed"})
        self.refunds.append((order_id, amount))
        return self._record("issue_refund", args, {"ok": True, "order_id": order_id, "amount": amount})
