""".vd write/read round trip and the Nelderim Lab server answering."""
import json, threading, urllib.request
from pathlib import Path
import pytest
from http.server import ThreadingHTTPServer

import numpy as np

from uo3d import vdread, vdwrite


def test_vd_round_trip(tmp_path):
    img = np.zeros((256, 256, 4), np.uint8)
    img[150:190, 110:140] = (200, 40, 40, 255)
    img[120:150, 120:132] = (40, 200, 40, 255)
    p = tmp_path / "t.vd"
    vdwrite.write_vd(str(p), {(4, 0): [img], (0, 2): [img, img]}, anim_type=2, anchor=(128, 192))
    at, n, A = vdread.read_vd(str(p))
    assert (at, n) == (2, 35)
    assert len(A[(0, 2)]) == 2 and (4, 1) not in A
    back = vdread.canvas(A[(4, 0)][0])
    assert np.array_equal(back[..., 3] > 0, img[..., 3] > 0)
    assert np.abs(back[img[..., 3] > 0, :3].astype(int) - img[img[..., 3] > 0, :3]).max() <= 8   # 15-bit colour


def test_app_server_state_and_page(tmp_path, monkeypatch, client):
    import nelderim_hub as H
    monkeypatch.setattr(H, "CONFIG_FILE", tmp_path / "cfg.json")
    H.save_config({"client": str(client), "output": str(tmp_path / "out")})
    import nelderim_app
    srv = ThreadingHTTPServer(("127.0.0.1", 0), nelderim_app.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        st = json.loads(urllib.request.urlopen(base + "/api/state").read())
        keys = [p["key"] for p in st["paths"]]
        assert keys == ["client", "toolkit", "output", "bodyglb", "studio", "blender"]
        assert next(p for p in st["paths"] if p["key"] == "client")["ok"]
        html = urllib.request.urlopen(base + "/").read().decode()
        assert "Nelderim Lab" in html
        png = urllib.request.urlopen(base + "/api/animslot/thumb?file=5&slot=32").read()
        assert png[:4] == b"\x89PNG"
    finally:
        srv.shutdown()


def _raw(base, method, path, headers=None, body=None):
    import http.client
    host, port = base.replace("http://", "").split(":")
    c = http.client.HTTPConnection(host, int(port))
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse(); data = r.read()
    return r.status, data


def test_server_rejects_other_web_pages(tmp_path, monkeypatch, client):
    """CSRF / DNS rebinding: only the app's own page (Host 127.0.0.1, same Origin, JSON POST) may use the API."""
    import nelderim_hub as H
    monkeypatch.setattr(H, "CONFIG_FILE", tmp_path / "cfg.json")
    H.save_config({"client": str(client), "output": str(tmp_path / "out")})
    import nelderim_app
    srv = ThreadingHTTPServer(("127.0.0.1", 0), nelderim_app.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    own = {"Origin": base, "Content-Type": "application/json"}
    try:
        assert _raw(base, "GET", "/api/state")[0] == 200
        assert _raw(base, "POST", "/api/deps", own, b"{}")[0] == 200
        assert _raw(base, "GET", "/api/state", {"Host": "evil.example"})[0] == 403          # DNS rebinding
        assert _raw(base, "GET", "/api/state", {"Origin": "https://evil.example"})[0] == 403
        assert _raw(base, "POST", "/api/deps", {"Origin": "https://evil.example", "Content-Type": "application/json"}, b"{}")[0] == 403
        assert _raw(base, "POST", "/api/deps", {"Content-Type": "text/plain"}, b"{}")[0] == 403   # "simple" cross-site POST
        assert _raw(base, "POST", "/api/open", own, json.dumps({"path": str(tmp_path)}).encode())[0] == 403  # file outside the app's folders
    finally:
        srv.shutdown()


def test_robe_from_gump_command_line():
    import nelderim_hub as H
    cfg = {"toolkit": "T", "client": "C"}
    a = H.cmd_robe_from_gump(cfg, "g.png", "szata_x", "Szata X", "0x2684", 970, no_hood=True, actions="4 0")["argv"]
    assert a[-1] == "0" and "--no-hood" in a
    i = a.index("--actions"); assert a[i + 1:i + 3] == ["4", "0"]
    assert a[a.index("--toolkit") + 1] == "T" and a[a.index("--key") + 1] == "szata_x"
    assert "robe_from_gump.py" in " ".join(a)


def test_app_js_is_valid_module():
    """app.js is an ES module; a stray raw newline in a string once broke the whole UI (node --check on a .js file does not catch it)."""
    import shutil, subprocess, tempfile
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    src = Path(__file__).resolve().parent.parent / "app" / "app.js"
    with tempfile.TemporaryDirectory() as d:
        mjs = Path(d) / "app.mjs"
        mjs.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        r = subprocess.run([node, "--check", str(mjs)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
