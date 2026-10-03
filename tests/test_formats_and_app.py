""".vd write/read round trip and the Nelderim Lab server answering."""
import json, threading, urllib.request
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
        assert keys == ["client", "toolkit", "output", "bodyglb"]
        assert next(p for p in st["paths"] if p["key"] == "client")["ok"]
        html = urllib.request.urlopen(base + "/").read().decode()
        assert "Nelderim Lab" in html
        png = urllib.request.urlopen(base + "/api/animslot/thumb?file=5&slot=32").read()
        assert png[:4] == b"\x89PNG"
    finally:
        srv.shutdown()
