"""uo3d with the UO_Model3D v13 body: baked Blender poses in the .glb (body_export.py), loose garments without cloth chains
(uo3d.hang, ported from UO_Model3D cloth_lib.py) and the per-item render options (uo3d.engine)."""
import json, os, struct, sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from test_creature import make_glb                  # noqa: E402
from uo3d import engine as E                        # noqa: E402
from uo3d import hang                               # noqa: E402
from uo3d.glbmodel import GLB                       # noqa: E402


def add_baked(path, mats, first):
    """append extras.uo3d.pose (as body_export.py writes it) for the clip 'Walk' of the test model"""
    d = open(path, "rb").read()
    n0 = struct.unpack_from("<I", d, 12)[0]
    js = json.loads(d[20:20 + n0]); binary = bytearray(d[20 + n0 + 8:])
    binary += b"\0" * (-len(binary) % 4)
    raw = np.asarray(mats, np.float32).tobytes()
    js["bufferViews"].append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(raw)})
    binary += raw
    js["buffers"][0]["byteLength"] = len(binary)
    js["extras"] = {"uo3d": {"version": 1, "nondeform": [], "bones": {"arm": {"head": [0, 1, 0], "tail": [0, 2, 0]}},
                             "pose": {"Walk": {"bufferView": len(js["bufferViews"]) - 1, "first": first, "count": len(mats)}}}}
    jb = json.dumps(js).encode(); jb += b" " * (-len(jb) % 4)
    out = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(jb) + 8 + len(binary))
    out += struct.pack("<I4s", len(jb), b"JSON") + jb + struct.pack("<I4s", len(binary), b"BIN\0") + bytes(binary)
    open(path, "wb").write(out)


def test_baked_pose_used_and_interpolated(tmp_path):
    p = str(tmp_path / "b.glb"); make_glb(p)
    A = np.eye(4); A[1, 3] = 1.0                                       # world matrix of joint 'arm' at rest (y = 1)
    B = A.copy(); B[0, 3] = 0.24                                       # frame 2: moved 24 cm along X
    add_baked(p, [[np.eye(4), A], [np.eye(4), B]], first=1)
    g = GLB(p)
    assert g.bones["arm"]["tail"] == [0, 2, 0]
    W = g.pose("Walk", 2 / 24.0)                                       # frame 2 = second baked frame
    assert abs(W[g.joints[1]][0, 3] - 0.24) < 1e-6
    W = g.pose("Walk", 1.5 / 24.0)                                     # halfway: linear
    assert abs(W[g.joints[1]][0, 3] - 0.12) < 1e-6
    SM = g.skin_matrices(g.pose("Walk", 2 / 24.0))
    assert np.allclose(SM[1], B @ g.ibm[1]) and np.allclose(SM[0], g.ibm[0])  # skinning uses the baked joint, the root stays


def test_cloak_bend_turns_below_the_shoulders_only():
    V = np.array([[0, 0.0, 1.5], [0, 0.0, 1.0], [0, 0.0, 0.2]])
    d = hang.cloak_bend(V, z_top=1.4, z_hem=0.2, y_top=0.0, d0=np.radians(20), d1=np.radians(20))
    assert np.allclose(d[0], 0)                                        # above the shoulder line: untouched
    assert d[1, 1] > 0.1 and d[2, 1] > d[1, 1]                         # tilted back (+Y), more at the hem


def test_hull_push_moves_cloth_out_of_a_leg():
    V = np.array([[0.0, -0.10, 0.4], [0.0, 0.25, 0.4], [0.0, -0.10, 1.1]])   # in front low, behind low, above the waist
    heads = np.array([[0.0, -0.15, 0.9]]); tails = np.array([[0.0, -0.30, 0.1]])  # a leg stepping forward (-Y)
    d = hang.hull_push(V, np.eye(4), heads, tails, np.array([0.07]), centre_xy=(0.0, 0.0), margin=0.05, kappa=0.8, z_top=1.0, z_hem=0.05)
    assert d[0, 1] < -0.05                                             # pushed forward, out past the leg
    assert np.allclose(d[1], 0) and np.allclose(d[2], 0)                # behind the body / at the waist: nothing


def test_render_options_contrast_edge_floor_and_near():
    img = np.zeros((5, 5, 4), np.uint8); img[1:4, 1:4] = (100, 100, 100, 255); img[2, 2, :3] = 200
    o = E.outline(img, 0.1, floor=24)
    assert o[1, 1, 0] == 24 and o[2, 2, 0] == 200                     # rim lifted to the floor, inside untouched
    c = E.contrast(img, 1.5, pivot=100 / 255)
    assert c[1, 1, 0] == 100 and c[2, 2, 0] == 250                     # pivot stays, the light gets lighter
    m = np.zeros((7, 7), bool); m[3, 3] = True
    n = E._near(m, 3)
    assert n[3, 3] == 1 and 0 < n[3, 4] < 1 and n[3, 6] == 0
    assert E.render_options("robe")["contrast"] == 1.5 and E.render_options("shirt")["contrast"] == 1.0
    assert E.render_options("robe", {"contrast": 1.0, "hide_erode": None})["contrast"] == 1.0
