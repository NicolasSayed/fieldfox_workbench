"""RPX layouts and checksum failures from a synthetic index builder."""
import struct
import zlib
import pytest
from fieldfox_recording import FieldFoxRecording, RecordingError
from fieldfox_recording.index import read_index
from fieldfox_recording.parser import inspect_path
from .fixtures import make_session


def index_bytes(count=3, extra=b"", version=1):
    body = struct.pack("<iB", 3, 10) + b"TRC"
    for tag, value in [(11, count), (12, 5000), (13, 100)]:
        body += struct.pack("<iBi", 4, tag, value)
    chunk = struct.pack("<i", len(body)) + b"FDAT" + body
    chunk += struct.pack("<I", zlib.crc32(b"FDAT" + body))
    return b"FFRPINDX" + struct.pack("<H", version) + chunk + extra


def test_index_count_crc_and_unknown_chunk(tmp_path):
    root = make_session(tmp_path / "session")
    chunk = struct.pack("<i4s", 3, b"TEST") + b"xyz" + struct.pack("<I", zlib.crc32(b"TESTxyz"))
    path = root / "TRC.rpx"
    path.write_bytes(index_bytes(extra=chunk))
    rec = FieldFoxRecording.open(root)
    assert rec.indexes[0]["stores"]["TRC"]["num_records"] == 3
    assert rec.indexes[0]["chunks"][1]["raw_body_hex"] == "78797a"
    assert inspect_path(path)["index"]["version"] == 1


def test_index_stale_count_rejected(tmp_path):
    root = make_session(tmp_path / "session")
    (root / "TRC.rpx").write_bytes(index_bytes(count=4))
    with pytest.raises(RecordingError, match="record count"):
        FieldFoxRecording.open(root)


@pytest.mark.parametrize("change", ["crc", "length", "truncated", "signature", "version"])
def test_bad_index(tmp_path, change):
    raw = bytearray(index_bytes())
    if change == "crc":
        raw[-1] ^= 1
    elif change == "length":
        struct.pack_into("<i", raw, 10, -1)
    elif change == "truncated":
        raw.pop()
    elif change == "signature":
        raw[0] = 0
    else:
        struct.pack_into("<H", raw, 8, 2)
    path = tmp_path / "bad.rpx"
    path.write_bytes(raw)
    with pytest.raises(RecordingError):
        read_index(path)
