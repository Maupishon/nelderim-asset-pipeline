"""Creature renderer: any skinned + animated .glb (no UO body) -> UO camera, 5 directions -> .vd type 0 (High, 22 actions) or 1 (Low, 13).

The model stands on Y=0 facing +Z (glTF convention; `face` turns other models), is scaled to `height` metres and centred over the
anchor. Animations are taken by name from the .glb (an action map says which clip is which UO action, how many frames, loop or not).
Lighting, outline, smoothing: the same code as the item renderer (engine.shade / outline / clean)."""
import io, json, math, os, time
import numpy as np

from . import raster as R
from . import statmesh
from .glbmodel import GLB
from .engine import shade, outline, clean, smooth_alpha, lift_dark, CANVAS, ANCHOR, say
from .vdwrite import write_vd, ACTIONS_BY_TYPE

TYPES = {"high": 0, "low": 1}
FACE_YAW = {"+z": 0.0, "-z": 180.0, "+x": -90.0, "-x": 90.0}   # degrees about Y that bring the model's front to +Z
DEFAULT_FRAMES = 8


class CreatureMesh:
    """what engine.shade wants from an item: tri, mesh (uv, mats, mat_of_tri, vcol), saturation, metal."""

    def __init__(self, g, saturation=1.0):
        self.tri = g.tri
        self.saturation, self.metal = saturation, None
        m = statmesh.Mesh()
        prim = g.js["meshes"][0]["primitives"][0]
        m.pos, m.nrm, m.tri = g.pos, g.nrm, g.tri
        m.uv = g.uv if g.uv is not None else np.zeros((len(g.pos), 2))
        mat = (g.js.get("materials") or [{}])[prim.get("material", 0)] if g.js.get("materials") else {}
        pbr = mat.get("pbrMetallicRoughness", {})
        tex = None
        png = g.texture_png() if "baseColorTexture" in pbr else None
        if png:
            try:
                tex = statmesh._image(png)
            except Exception:  # noqa: BLE001
                tex = None
        m.mats = [statmesh.Material(pbr.get("baseColorFactor", [0.7, 0.7, 0.7, 1.0]), tex, pbr.get("metallicFactor", 0.0))]
        m.mat_of_tri = np.zeros(len(g.tri), int)
        if "COLOR_0" in prim["attributes"]:
            vc = g.acc(prim["attributes"]["COLOR_0"]).astype(float)
            if vc.shape[1] == 3:
                vc = np.c_[vc, np.ones(len(vc))]
            m.vcol = vc / (255.0 if vc.max() > 1.5 else 1.0)
        self.mesh = m


def _yaw(P, deg):
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    return np.stack([P[:, 0] * c + P[:, 2] * s, P[:, 1], -P[:, 0] * s + P[:, 2] * c], 1)


class Creature:
    def __init__(self, path, height=1.8, face="+z", yaw=0.0, saturation=1.0):
        self.g = GLB(path)
        self.item = CreatureMesh(self.g, saturation)
        self.yaw = FACE_YAW[face] + yaw
        P, _ = self.g.skinned(None, 0.0)
        P = _yaw(P, self.yaw)
        lo, hi = P.min(0), P.max(0)
        self.scale = height / max(hi[1] - lo[1], 1e-6)
        self.origin = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])

    def pose(self, clip, t):
        P, N = self.g.skinned(clip, t)
        P, N = _yaw(P, self.yaw), _yaw(N, self.yaw)
        return (P - self.origin) * self.scale, N

    def frame(self, clip, t, d, smooth=0, outline_f=0.38, min_dark=0):
        W, H = CANVAS
        P, N = self.pose(clip, t)
        xy, z = R.camera(P, d, CANVAS, ANCHOR)
        tid, _ = R.raster(xy, z, self.item.tri, W, H)
        if not (tid >= 0).any():
            return np.zeros((H, W, 4), np.uint8)
        img = shade(self.item, tid, W, H, xy, R.rotate_normals(N, d))
        if smooth:
            img = smooth_alpha(img, smooth)
        return lift_dark(clean(outline(img, outline_f)), min_dark)


def clip_time(dur, k, n, loop):
    """time of UO frame k of n: a loop does not repeat its first pose at the end, anything else runs start..end."""
    if n <= 1:
        return 0.0
    return dur * k / n if loop else dur * k / (n - 1)


def render(path, actions, out_path, anim_type="high", height=1.8, face="+z", yaw=0.0, smooth=0, outline_f=0.38,
           min_dark=0, progress=None):
    """actions: {uo_action: {"clip": name, "frames": n, "loop": bool}} -> writes the .vd, returns {(action, dir): [frames]}."""
    at = TYPES[anim_type]
    cr = Creature(path, height, face, yaw)
    n_act = ACTIONS_BY_TYPE[at]
    blocks, t0 = {}, time.time()
    total = sum(5 * int(v.get("frames", DEFAULT_FRAMES)) for v in actions.values()); done = 0
    for a, spec in sorted(actions.items()):
        if not 0 <= int(a) < n_act:
            raise ValueError(f"akcja {a} poza zakresem 0..{n_act - 1} dla typu {anim_type}")
        clip = spec["clip"]
        if clip not in cr.g.anims:
            raise ValueError(f"w modelu nie ma animacji „{clip}” (są: {', '.join(cr.g.anims) or 'brak'})")
        dur, n = cr.g.duration(clip), int(spec.get("frames", DEFAULT_FRAMES))
        loop = bool(spec.get("loop", False))
        for k in range(n):
            t = clip_time(dur, k, n, loop)
            for d in range(5):
                blocks.setdefault((int(a), d), []).append(cr.frame(clip, t, d, smooth, outline_f, min_dark))
                done += 1
            if progress:
                progress(done, total)
    write_vd(out_path, blocks, anim_type=at, anchor=(128, 192))
    say(f"zapisano {out_path} ({done} klatek, {time.time() - t0:.0f} s)")
    return blocks


def load_actions(path):
    """JSON: {"0": {"clip": "Walk", "frames": 10, "loop": true}, "1": "Idle", ...}; a bare string = clip with defaults."""
    raw = json.load(open(path, encoding="utf-8"))
    out = {}
    for k, v in raw.items():
        if k.startswith("_"):
            continue
        out[int(k)] = {"clip": v} if isinstance(v, str) else dict(v)
    return out


PROMPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "creature_prompts.json")


def action_template(anim_type="high", clip_names=None):
    """action map for `anim_type` from examples/creature_prompts.json: every UO action with its prompt, default frames and loop.
    clip_names (optional {action: clip}) fills in the model's clips; otherwise "clip" is the UO group name to be renamed."""
    tab = json.load(open(PROMPTS, encoding="utf-8"))[anim_type]
    out = {}
    for k, v in tab.items():
        out[k] = dict(v, clip=(clip_names or {}).get(int(k)) or v["name"])
    return out
