import codecs
import threading

import pytest

from fieldfox_browser.client import BrowserError, Cancelled, FieldFoxClient
from fieldfox_browser.preview import PREVIEW_BYTES, make_preview, preview_local
from .browser.fake_instrument import instrument, SESSION
from .test_workbench import desktop


@pytest.mark.parametrize("encoding,bom", [("utf-8", b""), ("utf-8", codecs.BOM_UTF8),
                                        ("utf-16-le", codecs.BOM_UTF16_LE), ("utf-16-be", codecs.BOM_UTF16_BE),
                                        ("utf-32-le", codecs.BOM_UTF32_LE)])
def test_text_preview_encodings(encoding, bom):
    data = bom + "Frequency,Power\n1000000,-70\nCafé\n".encode(encoding)
    result = make_preview(data, len(data))
    assert result.kind == "text" and "Café" in result.text and "read-only" in result.description


def test_preview_is_plain_text_and_handles_partial_utf8():
    data = b'<script>never executed</script>\n'+"Aé".encode()
    result = make_preview(data[:-1], len(data))
    assert result.text.endswith("A") and "prefix only" in result.description
    assert "<script>" in result.text


def test_binary_preview_is_bounded_hex_and_cp1252_text():
    data = bytes(range(256))*40
    result = make_preview(data, len(data))
    assert result.kind == "binary" and result.bytes_shown == 4096
    assert result.text.startswith("00000000  00 01 02") and "prefix only" in result.description
    assert make_preview(b'\x93quoted\x94', 8).kind == "text"


def test_preview_local_and_limits(tmp_path):
    file = tmp_path / "large.csv"; file.write_bytes(b"x"*(PREVIEW_BYTES+100))
    result = preview_local(file)
    assert result.bytes_read == PREVIEW_BYTES and result.size == PREVIEW_BYTES+100
    with pytest.raises(ValueError): make_preview(b"x"*(PREVIEW_BYTES+1), PREVIEW_BYTES+1)
    with pytest.raises(ValueError): make_preview(b"123", 2)
    assert make_preview(b"", 0).text == ""


def test_remote_preview_prefix_closes_stream_and_next_query_works(monkeypatch):
    import fieldfox_browser.client as client_module
    original_connect = client_module.socket.create_connection
    connections = []
    class ObservedSocket:
        def __init__(self, socket):
            self.socket = socket; self.received = 0; self.closed = False
        def __getattr__(self, name): return getattr(self.socket, name)
        def recv(self, count):
            data = self.socket.recv(count); self.received += len(data); return data
        def close(self): self.closed = True; self.socket.close()
    def connect(*args, **kwargs):
        connection = ObservedSocket(original_connect(*args, **kwargs))
        connections.append(connection); return connection
    monkeypatch.setattr(client_module.socket, "create_connection", connect)
    with instrument() as fake:
        remote = SESSION+"\\large.csv"; fake.files[remote] = b"Header,Value\n"+b"x"*(PREVIEW_BYTES*2)
        client = FieldFoxClient("127.0.0.1", fake.port, 1)
        data, size = client.read_prefix(remote, max_bytes=128)
        assert len(data) == 128 and size == len(fake.files[remote])
        assert connections[0].closed
        assert connections[0].received == 2+len(str(size))+128  # header + exact payload prefix
        assert "N9917B" in client.identify()
        assert len(connections) == 2 and connections[1].closed
        assert not any(c.startswith(("MMEM:DEL", "MMEM:STOR")) for c in fake.commands)


def test_remote_preview_fragmentation_changed_length_corruption_and_cancel():
    with instrument() as fake:
        remote = SESSION+"\\example.txt"; fake.files[remote] = b"hello\nworld\n"; fake.fragment = True
        client = FieldFoxClient("127.0.0.1", fake.port, 1)
        assert client.read_prefix(remote) == (b"hello\nworld\n", 12)
        with pytest.raises(BrowserError, match="size changed"): client.read_prefix(remote, expected_size=1)
        fake.fault = "terminator"
        with pytest.raises(BrowserError, match="terminator"): client.read_prefix(remote)
        cancel = threading.Event(); cancel.set()
        with pytest.raises(Cancelled): client.read_prefix(remote, cancel=cancel)
        with pytest.raises(BrowserError): client.read_prefix(remote, max_bytes=2*1024**2)


def test_explorer_preview_remote_local_search_and_help(desktop, tmp_path):
    app, errors, finish = desktop
    assert "Help" not in [app.tabs.tab(tab, "text") for tab in app.tabs.tabs()]
    app.show_help(); first = app.help_window; app.show_help()
    assert first is app.help_window and app.help_text.cget("state") == "disabled"
    first.destroy()
    with instrument() as fake:
        remote = SESSION+"\\readme.txt"; fake.files[remote] = b"FieldFox TEST ONLY\nFrequency,Power\n1,-70\n2,-60\n"
        app.browser.host.set("127.0.0.1"); app.browser.port.set(str(fake.port)); app.browser.path.set(SESSION)
        app.browser.browse(); finish()
        item = next(i for i, e in app.browser.entries.items() if e.name == "readme.txt")
        app.browser.tree.selection_set(item); app.root.update(); app.browser.preview_selected(); finish()
        assert app.browser.preview_result.kind == "text" and app.browser.preview_text.cget("state") == "disabled"
        assert "TEST ONLY" in app.browser.preview_text.get("1.0", "end")
        app.browser.preview_query.set("Frequency"); app.browser.find_preview()
        assert app.browser.preview_text.tag_ranges("match")
    local = tmp_path / "notes.txt"; local.write_text("Local text preview", encoding="utf-8")
    app.browser.open_local_preview(local); finish()
    assert "Local text" in app.browser.preview_text.get("1.0", "end") and not errors


def test_stale_preview_does_not_replace_new_selection(desktop):
    app, errors, finish = desktop
    with instrument() as fake:
        for name in ("one.txt", "two.txt"): fake.files[SESSION+"\\"+name] = name.encode()
        app.browser.host.set("127.0.0.1"); app.browser.port.set(str(fake.port)); app.browser.path.set(SESSION)
        app.browser.browse(); finish()
        items = {e.name: i for i, e in app.browser.entries.items()}
        app.browser.tree.selection_set(items["one.txt"]); app.root.update(); app.browser.preview_selected()
        app.browser.tree.selection_set(items["two.txt"]); app.root.update()
        finish()
        app.browser.preview_selected(); finish()
        assert app.browser.preview_name.get() == "two.txt" and app.browser.preview_result.text == "two.txt"
        assert not errors
