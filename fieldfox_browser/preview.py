"""Read-only, bounded text and hex previews; no content is executed or parsed."""
from dataclasses import dataclass
from pathlib import Path
import codecs

PREVIEW_BYTES = 256*1024
HEX_BYTES = 4096


@dataclass(frozen=True)
class FilePreview:
    text: str
    kind: str
    encoding: str
    size: int
    bytes_read: int
    bytes_shown: int

    @property
    def description(self):
        kind = self.encoding if self.kind == "text" else "Binary · hex view"
        suffix = " · prefix only" if self.bytes_shown < self.size else ""
        return f"{kind} · {self.bytes_shown:,} / {self.size:,} bytes{suffix} · read-only"


def make_preview(data: bytes, size: int) -> FilePreview:
    if len(data) > PREVIEW_BYTES or size < len(data): raise ValueError("Preview data exceeds its bounded prefix or declared size.")
    encoding = "utf-8"
    for marker, candidate in [(codecs.BOM_UTF32_LE, "utf-32"), (codecs.BOM_UTF32_BE, "utf-32"),
                              (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16"),
                              (codecs.BOM_UTF8, "utf-8-sig")]:
        if data.startswith(marker): encoding = candidate; break
    try:
        text = codecs.getincrementaldecoder(encoding)(errors="strict").decode(data, final=len(data) == size)
    except UnicodeDecodeError:
        if encoding != "utf-8": text = None
        else:
            try: text = data.decode("cp1252"); encoding = "Windows-1252"
            except UnicodeDecodeError: text = None
    if text is not None and ("\x00" in text or sum(not(c.isprintable() or c in "\r\n\t") for c in text) > len(text)*.02): text = None
    if text is not None:
        # Make control characters visible; Text is always read-only/plain text.
        text = "".join(c if c.isprintable() or c in "\r\n\t" else f"\\u{ord(c):04x}" for c in text)
        return FilePreview(text, "text", encoding, size, len(data), len(data))
    data_to_show = data[:HEX_BYTES]; lines = []
    for offset in range(0, len(data_to_show), 16):
        row = data_to_show[offset:offset+16]
        hexes = " ".join(f"{v:02X}" for v in row)
        chars = "".join(chr(v) if 32 <= v < 127 else "." for v in row)
        lines.append(f"{offset:08X}  {hexes:<47}  {chars}")
    return FilePreview("\n".join(lines), "binary", "", size, len(data), len(data_to_show))


def preview_local(path):
    path = Path(path)
    with path.open("rb") as stream:
        import os
        size = os.fstat(stream.fileno()).st_size
        data = stream.read(PREVIEW_BYTES)
    return make_preview(data, max(size, len(data)))
