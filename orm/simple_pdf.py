"""A tiny PDF writer for text reports (A4, Helvetica, word-wrapped).

Written by hand so the audit pack needs no extra package. It handles what a
text report needs: headings, wrapped paragraphs, bold lines and page breaks,
in the Windows-1252 character set (Latin letters, quotes, dashes, the middle
dot). Characters outside it print as '?'.
"""
from __future__ import annotations

PAGE_W, PAGE_H = 595.28, 841.89          # A4 in points
MARGIN = 50
_AVG = 0.50                              # average Helvetica glyph width, in em
_BOLD_AVG = 0.55


def _esc(text: str) -> bytes:
    raw = text.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


class Document:
    def __init__(self) -> None:
        self.pages: list[list[bytes]] = [[]]
        self.y = PAGE_H - MARGIN

    def _ensure(self, height: float) -> None:
        if self.y - height < MARGIN:
            self.pages.append([])
            self.y = PAGE_H - MARGIN

    def _wrap(self, text: str, size: float, bold: bool) -> list[str]:
        per_line = max(20, int((PAGE_W - 2 * MARGIN) / (size * (_BOLD_AVG if bold else _AVG))))
        lines: list[str] = []
        for para in str(text).splitlines() or [""]:
            words, line = para.split(), ""
            for w in words:
                while len(w) > per_line:            # very long tokens (URLs)
                    if line:
                        lines.append(line)
                        line = ""
                    lines.append(w[:per_line])
                    w = w[per_line:]
                if len(line) + len(w) + (1 if line else 0) > per_line:
                    lines.append(line)
                    line = w
                else:
                    line = f"{line} {w}" if line else w
            lines.append(line)
        return lines

    def text(self, text: str, *, size: float = 10, bold: bool = False) -> None:
        leading = size * 1.35
        font = b"/F2" if bold else b"/F1"
        for line in self._wrap(text, size, bold):
            self._ensure(leading)
            self.y -= leading
            self.pages[-1].append(
                b"BT " + font + b" %.1f Tf %.2f %.2f Td (" % (size, MARGIN, self.y)
                + _esc(line) + b") Tj ET")

    def heading(self, text: str, size: float = 16) -> None:
        self._ensure(size * 2.2)
        self.y -= size * 0.4
        self.text(text, size=size, bold=True)
        self.y -= size * 0.3

    def space(self, points: float) -> None:
        self.y -= points

    def render(self) -> bytes:
        objects: list[bytes] = []

        def add(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        catalog = add(b"")          # filled in below
        pages_id = add(b"")
        f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                 b"/Encoding /WinAnsiEncoding >>")
        f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                 b"/Encoding /WinAnsiEncoding >>")
        kids = []
        total = len(self.pages)
        for n, ops in enumerate(self.pages, 1):
            footer = (b"BT /F1 8 Tf %.2f %.2f Td (" % (MARGIN, MARGIN / 2)
                      + _esc(f"Clausewiz audit pack  ·  page {n} of {total}") + b") Tj ET")
            stream = b"\n".join(ops + [footer])
            content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream
                          + b"\nendstream")
            kids.append(add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] "
                b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> "
                b"/Contents %d 0 R >>" % (pages_id, PAGE_W, PAGE_H, f1, f2, content)))
        objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id
        objects[pages_id - 1] = (b"<< /Type /Pages /Kids [" +
                                 b" ".join(b"%d 0 R" % k for k in kids) +
                                 b"] /Count %d >>" % len(kids))
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, body in enumerate(objects, 1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
        for off in offsets:
            out += b"%010d 00000 n \n" % off
        out += (b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
                % (len(objects) + 1, catalog, xref))
        return bytes(out)
