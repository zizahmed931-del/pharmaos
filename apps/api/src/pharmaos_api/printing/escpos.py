"""ESC/POS receipt builder + raw sender (Phase 0 / M12 walking skeleton).

CLAUDE.md printing architecture: 80mm thermal receipts + cash drawer go over
RAW ESC/POS (never browser printing). In production the Electron main process
owns the transport (USB/network); this module provides the byte stream and a
network (port 9100) sender so the slice is testable end-to-end. Printing never
depends on the internet.

Arabic text: sent as UTF-8. Thermal printers vary in Arabic firmware support —
the approved-hardware matrix test (real device, user-side) decides per model
whether native UTF-8, a codepage, or bitmap rendering is used. The byte
protocol below (init/feed/cut/drawer) is model-independent.
"""

import socket
from dataclasses import dataclass
from decimal import Decimal

# Core ESC/POS commands
INIT = b"\x1b@"  # ESC @  — initialize
ALIGN_LEFT = b"\x1ba\x00"
ALIGN_CENTER = b"\x1ba\x01"
ALIGN_RIGHT = b"\x1ba\x02"
BOLD_ON = b"\x1bE\x01"
BOLD_OFF = b"\x1bE\x00"
DOUBLE_SIZE = b"\x1d!\x11"  # GS ! — double width+height
NORMAL_SIZE = b"\x1d!\x00"
FEED = b"\n"
CUT = b"\x1dV\x42\x03"  # GS V B — partial cut with feed
DRAWER_PULSE = b"\x1bp\x00\x19\xfa"  # ESC p — open cash drawer (pin 2)

_LINE_WIDTH = 42  # characters at font A on 80mm paper


@dataclass(frozen=True)
class ReceiptLine:
    name: str
    quantity: Decimal
    unit_name: str
    line_total: Decimal


@dataclass(frozen=True)
class ReceiptData:
    pharmacy_name: str
    branch_name: str
    invoice_number: str
    created_at_display: str
    lines: list[ReceiptLine]
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    currency_symbol: str
    thank_you_message: str


def _text(value: str) -> bytes:
    return value.encode("utf-8")


def _amount_row(label: str, amount: Decimal, symbol: str) -> bytes:
    amount_text = f"{amount:.2f} {symbol}"
    padding = max(1, _LINE_WIDTH - len(label) - len(amount_text))
    return _text(label + " " * padding + amount_text) + FEED


def build_receipt(receipt: ReceiptData, *, open_drawer: bool = True) -> bytes:
    """Render the full ESC/POS byte stream for an 80mm receipt."""
    out = bytearray()
    out += INIT

    out += ALIGN_CENTER + DOUBLE_SIZE + BOLD_ON
    out += _text(receipt.pharmacy_name) + FEED
    out += NORMAL_SIZE + BOLD_OFF
    out += _text(receipt.branch_name) + FEED
    out += _text("-" * _LINE_WIDTH) + FEED

    out += ALIGN_RIGHT
    out += _text(f"فاتورة: {receipt.invoice_number}") + FEED
    out += _text(receipt.created_at_display) + FEED
    out += _text("-" * _LINE_WIDTH) + FEED

    out += ALIGN_RIGHT
    for line in receipt.lines:
        out += _text(line.name) + FEED
        qty = f"{line.quantity.normalize()} × {line.unit_name}"
        out += _amount_row(qty, line.line_total, receipt.currency_symbol)
    out += _text("-" * _LINE_WIDTH) + FEED

    out += _amount_row("الإجمالي الفرعي", receipt.subtotal, receipt.currency_symbol)
    if receipt.discount:
        out += _amount_row("الخصم", receipt.discount, receipt.currency_symbol)
    out += BOLD_ON + DOUBLE_SIZE
    out += _amount_row("الإجمالي", receipt.total, receipt.currency_symbol)
    out += NORMAL_SIZE + BOLD_OFF

    out += ALIGN_CENTER + FEED
    out += _text(receipt.thank_you_message) + FEED
    out += FEED * 3
    out += CUT
    if open_drawer:
        out += DRAWER_PULSE
    return bytes(out)


def send_raw(payload: bytes, *, host: str, port: int = 9100, timeout: float = 5.0) -> None:
    """Send raw bytes to a network ESC/POS printer (JetDirect port 9100).

    USB transport is owned by the Electron main process in production
    (Phase 1); network printing works from any process.
    """
    with socket.create_connection((host, port), timeout=timeout) as conn:
        conn.sendall(payload)
