"""uo3d creature renderer: a synthetic skinned + animated .glb (a two-bone column) -> .vd type 0 / 1."""
import json, os, struct, sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from uo3d import creature as C                       # noqa: E402
from uo3d import vdread                              # noqa: E402


def make_glb(path):
    ring = [(-0.3, -0.3), (0.3, -0.3), (0.3, 0.3), (-0.3, 0.3)]
    pos, nrm, jnt, wgt = [], [], [], []
    for y in (0.0, 1.0, 2.0):
        for x, z in ring:
            pos.append((x, y, z)); n = np.array([x, 0, z]); nrm.append(tuple(n / np.linalg.norm(n)))
            j = 0 if y < 1.5 else 1
            jnt.append((j, 0, 0, 0)); wgt.append((1.0, 0, 0, 0))
    tri = []
    for r in range(2):
        for i in range(4):
            a, b = r * 4 + i, r * 4 + (i + 1) % 4
            tri += [(a, b, a + 4), (b, b + 4, a + 4)]
    tri += [(8, 10, 9), (8, 11, 10)]                                       # top cap
    blobs, views, accs = [], [], []

    def add(arr, ctype, typ, count, target=None):
        data = np.ascontiguousarray(arr).tobytes()
        off = sum(len(b) for b in blobs)
        blobs.append(data + b"\0" * (-len(data) % 4))
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(data)})
        accs.append({"bufferView": len(views) - 1, "componentType": ctype, "count": count, "type": typ})
        return len(accs) - 1

    P = np.array(pos, np.float32)
    a_pos = add(P, 5126, "VEC3", len(P)); accs[a_pos]["min"] = P.min(0).tolist(); accs[a_pos]["max"] = P.max(0).tolist()
    a_nrm = add(np.array(nrm, np.float32), 5126, "VEC3", len(P))
    a_jnt = add(np.array(jnt, np.uint8), 5121, "VEC4", len(P))
    a_wgt = add(np.array(wgt, np.float32), 5126, "VEC4", len(P))
    a_idx = add(np.array(tri, np.uint16).reshape(-1), 5123, "SCALAR", len(tri) * 3)
    ibm = np.stack([np.eye(4, dtype=np.float32), np.eye(4, dtype=np.float32)])
    ibm[1][1, 3] = -1.0                                                     # column-major: translation (0,-1,0) for joint at y=1
    a_ibm = add(ibm.reshape(-1), 5126, "MAT4", 2)
    t = np.array([0.0, 0.5, 1.0], np.float32)
    q = np.array([[0, 0, 0, 1], [0, 0, np.sin(0.4), np.cos(0.4)], [0, 0, 0, 1]], np.float32)
    a_t, a_q = add(t, 5126, "SCALAR", 3), add(q, 5126, "VEC4", 3)
    js = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0, 1]}],
          "nodes": [{"mesh": 0, "skin": 0, "name": "mesh"},
                    {"name": "root", "children": [2]},
                    {"name": "arm", "translation": [0, 1, 0]}],
          "meshes": [{"primitives": [{"attributes": {"POSITION": a_pos, "NORMAL": a_nrm, "JOINTS_0": a_jnt, "WEIGHTS_0": a_wgt}, "indices": a_idx}]}],
          "skins": [{"joints": [1, 2], "inverseBindMatrices": a_ibm}],
          "animations": [{"name": "Walk", "samplers": [{"input": a_t, "output": a_q, "interpolation": "LINEAR"}],
                          "channels": [{"sampler": 0, "target": {"node": 2, "path": "rotation"}}]}],
          "accessors": accs, "bufferViews": views, "buffers": [{"byteLength": sum(len(b) for b in blobs)}]}
    jb = json.dumps(js).encode(); jb += b" " * (-len(jb) % 4)
    bb = b"".join(blobs)
    out = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(jb) + 8 + len(bb))
    out += struct.pack("<I4s", len(jb), b"JSON") + jb + struct.pack("<I4s", len(bb), b"BIN\0") + bb
    open(path, "wb").write(out)


def test_clip_time_loop_and_one_shot():
    assert C.clip_time(1.0, 0, 4, True) == 0.0 and abs(C.clip_time(1.0, 3, 4, True) - 0.75) < 1e-9
    assert abs(C.clip_time(1.0, 3, 4, False) - 1.0) < 1e-9 and C.clip_time(1.0, 0, 1, False) == 0.0


def test_render_high_and_low(tmp_path):
    glb = tmp_path / "c.glb"; make_glb(str(glb))
    for kind, n_act in (("high", 22), ("low", 13)):
        out = tmp_path / f"{kind}.vd"
        blocks = C.render(str(glb), {0: {"clip": "Walk", "frames": 4, "loop": True}, 1: {"clip": "Walk", "frames": 1}},
                          str(out), kind, height=1.6)
        assert len(blocks[(0, 0)]) == 4 and len(blocks[(1, 4)]) == 1
        d = open(out, "rb").read()
        magic, typ = struct.unpack_from("<hh", d, 0)
        assert magic == 6 and typ == (0 if kind == "high" else 1)
        used = [i for i in range(n_act * 5) if struct.unpack_from("<iii", d, 4 + 12 * i)[0] > 0]
        assert used == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]                  # actions 0 and 1, five directions each


def test_model_is_scaled_grounded_and_animated(tmp_path):
    glb = tmp_path / "c.glb"; make_glb(str(glb))
    cr = C.Creature(str(glb), height=1.6)
    P, _ = cr.pose(None, 0.0)
    assert abs(P[:, 1].min()) < 1e-6 and abs(np.ptp(P[:, 1]) - 1.6) < 1e-6
    assert abs(P[:, 0].mean()) < 1e-6
    P2, _ = cr.pose("Walk", 0.5)
    assert np.abs(P2 - P).max() > 0.05                                  # the arm joint really moves the top half
    img = cr.frame("Walk", 0.0, 0)
    ys, xs = np.nonzero(img[..., 3])
    assert 40 < ys.max() - ys.min() < 80 and abs(ys.max() - 192) < 14  # about 1.6 m on screen, feet near the anchor row (the box has depth)


def test_missing_clip_and_bad_action_are_reported(tmp_path):
    glb = tmp_path / "c.glb"; make_glb(str(glb))
    for acts, msg in (({0: {"clip": "Nope"}}, "Nope"), ({30: {"clip": "Walk"}}, "poza zakresem")):
        try:
            C.render(str(glb), acts, str(tmp_path / "x.vd"), "high")
            assert False
        except ValueError as e:
            assert msg in str(e)


def test_load_actions_accepts_bare_strings(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"_opis": "x", "0": {"clip": "Walk", "frames": 10, "loop": True}, "1": "Idle"}), encoding="utf-8")
    a = C.load_actions(str(p))
    assert a == {0: {"clip": "Walk", "frames": 10, "loop": True}, 1: {"clip": "Idle"}}


def test_prompt_table_covers_every_action_and_loads_as_an_action_map(tmp_path):
    import json
    from uo3d import cli_creature
    for kind, n in (("high", 22), ("low", 13)):
        t = C.action_template(kind)
        assert sorted(map(int, t)) == list(range(n))
        assert all(v["prompt"].startswith("An object") and v["frames"] >= 1 for v in t.values())
        out = tmp_path / f"{kind}.json"
        assert cli_creature.main(["--template", kind, "--out", str(out)]) == 0
        loaded = C.load_actions(str(out))
        assert len(loaded) == n and loaded[0]["loop"] is True
    assert C.action_template("high", {0: "Walk_L"})["0"]["clip"] == "Walk_L"
