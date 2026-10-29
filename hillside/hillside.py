"""Headless: Hillside, a 12-point circuit with two rises, built with the OAG add-on and dressed
with art (ADR-0076). Pulse 03_Track's road, wall, grass, rock, tree, sea and start-line textures
and its sky are named (host references; no pixels leave the disc). Own geometry: terrain, a lake
inside the loop, a ridged mountain range all round (grass, rock, snow by height), rocks, trees and
bushes, three airships, a covered bend that darkens the ships, a start gantry with the laser line
and eight painted grid slots, chevrons before the bends. 4 speed and 5 weapon pads. A Sun lamp
casting shadows, a fill light for the ships, an ambient, a lens flare with an own atlas, and a
Cycles bake of sun + sky + bounce into every art mesh's COLOR_0.

Everything here is chosen, not measured. Rebuild into tracks/ with Blender 4.2+:

    blender -b --factory-startup --python-exit-code 1 --python hillside.py -- tracks [--samples N]

OAG_ADDON_DIR names the add-on's parent directory (default: the engine checkout this repo is
mounted in as assets/mods/examples, i.e. ../../../../scripts/blender from here).
"""

import math
import os
import random
import struct
import sys
import time
import zlib

ADDON = os.environ.get(
    "OAG_ADDON_DIR",
    os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "scripts", "blender")),
)
sys.path.insert(0, ADDON)
import bpy
from mathutils import Vector

import oag_track
from oag_track import f32, scene

args = sys.argv[sys.argv.index("--") + 1 :]
out = args[0]
SAMPLES = int(args[args.index("--samples") + 1]) if "--samples" in args else 96
os.makedirs(out, exist_ok=True)

CONTROL = [
    (-1300, -200, 0),
    (-1000, -650, 20),
    (-400, -750, 60),
    (200, -600, 90),
    (700, -750, 60),
    (1250, -450, 20),
    (1350, 150, 0),
    (900, 550, 0),
    (300, 350, 30),
    (-300, 650, 60),
    (-900, 700, 30),
    (-1300, 350, 0),
]
HOST = "Data\\Environments\\03_Track\\track.vex"
TEX = "Data\\Environments\\03_Track\\Textures\\"
GENERIC = "Data\\Environments\\GenericTrackTextures\\"  # Pulse's shared road and wall set
COVER = range(84, 95)  # spline points under the covered stretch (the low bend)
COVER_LIGHT = 110  # the light scale byte under it (ambient and sun)
ROOF_HEIGHT = 62.0
PILLAR_OFFSET = 50.0
WALL_HEIGHT = 5.0  # Pulse 03_Track: the barrier art peaks at 5 units above the road, collision walls under 5.2
HALF_WIDTH = 28.0
UP = Vector((0.0, 0.0, 1.0))

# Albedos for the bake's bounce only (the textures are on the disc, not in Blender).
ALBEDO = {
    "road": (0.30, 0.30, 0.31),
    "wall": (0.45, 0.45, 0.45),
    "terrain": (0.20, 0.30, 0.12),
    "rock": (0.42, 0.40, 0.36),
    "tree": (0.12, 0.25, 0.08),
    "roof": (0.40, 0.40, 0.42),
    "decal": (0.45, 0.45, 0.45),
    "water": (0.10, 0.16, 0.20),
    "snow": (0.85, 0.87, 0.90),
}


def png(path, size, pixel):
    rows = b""
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            row += bytes(pixel(x, y))
        rows += bytes(row)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(data)


def flare_pixel(x, y):
    """The 2x2 flare atlas (docs/rendering/lens-flare.md): cell 0 the sun's glow, 1 a soft
    disc, 2 a halo ring, 3 a hexagon. White; the ring law tints it."""
    c = (x >= 32) + 2 * (y >= 32)
    u, v = (x % 32 - 15.5) / 15.5, (y % 32 - 15.5) / 15.5
    r = math.hypot(u, v)
    if c == 0:
        a = max(0.0, 1.0 - r) ** 2
    elif c == 1:
        a = max(0.0, 1.0 - r**4) * 0.8
    elif c == 2:
        a = max(0.0, 1.0 - abs(r - 0.78) / 0.14) * 0.9
    else:
        ang = math.atan2(v, u)
        hexr = math.cos(math.pi / 6) / math.cos((ang % (math.pi / 3)) - math.pi / 6)
        a = 0.7 if r <= 0.9 * hexr else max(0.0, 0.7 - (r - 0.9 * hexr) * 6)
    a = min(1.0, a) * (1.0 if c == 0 else 0.55)
    return (round(200 * a), round(200 * a), round(200 * a), round(255 * a))


def chevron_pixel(x, y):
    """A painted chevron: amber, alpha 0 off the stripe; points along +u."""
    u, v = x / 63.0, y / 63.0
    d = (u - 0.25) - abs(v - 0.5) * 0.8
    on = 0.0 <= (d % 0.5) < 0.22 and 0.08 < v < 0.92
    return (250, 170, 30, 220) if on else (0, 0, 0, 0)


bpy.ops.wm.read_factory_settings(use_empty=True)
oag_track.register()
ctx = bpy.context
sc = ctx.scene

# The simulation half: exactly the plain Hillside's calls.
curve = bpy.data.curves.new("centre line", "CURVE")
curve.dimensions = "3D"
sp = curve.splines.new("BEZIER")
sp.bezier_points.add(len(CONTROL) - 1)
for p, (x, y, z) in zip(sp.bezier_points, CONTROL):
    p.co = (x, -y, z)
    p.handle_left_type = p.handle_right_type = "AUTO"
sp.use_cyclic_u = True
line = bpy.data.objects.new("centre line", curve)
sc.collection.objects.link(line)
line["oag_kind"] = "spline"
line.oag_points = 160
line.oag_half_width = HALF_WIDTH
line.oag_wall_height = WALL_HEIGHT
ctx.view_layer.objects.active = line
sc.oag_track_id = "hillside"
sc.oag_track_title = "Hillside"
sc.oag_track_host = "wipeout-pulse"
sc.oag_track_notes = (
    "12 control points, two rises (chosen, not measured); authored headless with the OAG add-on\n"
    "art: Pulse 03_Track's textures and sky by name, own terrain, props and a covered bend, "
    "Cycles-baked sun, sky and bounce (chosen, not measured)"
)
assert bpy.ops.oag.build_ribbon() == {"FINISHED"}
assert bpy.ops.oag.add_start() == {"FINISHED"}
# Pads: speedups on the straights, weapon pads spread round the lap (cursor positions on the
# centre line, Blender's x/y; each snaps to the nearest spline point). Chosen, not measured.
for kind, (x, y, z) in (
    ("speedup", (700, 750, 60)),
    ("speedup", (-750, 0, 0)),
    ("speedup", (1300, -150, 10)),
    ("speedup", (-600, -675, 45)),
    ("weapon", (-1300, -350, 0)),
    ("weapon", (-100, 675, 75)),
    ("weapon", (975, 600, 40)),
    ("weapon", (600, -450, 15)),
    ("weapon", (-1100, -700, 15)),
):
    sc.cursor.location = (x, y, z)
    assert bpy.ops.oag.add_pad(kind=kind) == {"FINISHED"}
line.oag_cover_light = COVER_LIGHT

path = scene.path_of(line, ctx.evaluated_depsgraph_get(), 0)
P = path.points
N = len(P)


def B(v):
    return Vector(scene.to_blender(v))


pos = [B(q.pos) for q in P]
lat = [B(q.lateral) for q in P]
up = [B(f32.unit(f32.cross(q.lateral, q.tangent))) for q in P]
if up[0].z < 0:
    up = [-u for u in up]
dist = [0.0]
for i in range(1, N + 1):
    dist.append(dist[-1] + (pos[i % N] - pos[i - 1]).length)

# Images: host references carry a name and no pixels; own ones are PNG files.
IMAGES = {}


def host(name, folder=TEX):
    """A Texture node of 03_Track by its full asset path (names read off the disc with
    oag-raceplay's export_track example)."""
    if name not in IMAGES:
        img = bpy.data.images.new(name, 8, 8)
        img["oag_host_entry"] = HOST
        img["oag_host_name"] = folder + name
        IMAGES[name] = img
    return IMAGES[name]


def own(name, size, pixel):
    path = os.path.join(out, name)
    png(path, size, pixel)
    img = bpy.data.images.load(path)
    IMAGES[name] = img
    return img


MATS = {}


def material(key, image, kind, blend="opaque", clip=None, culled=True):
    if key in MATS:
        return MATS[key]
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    m.use_backface_culling = culled
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = image
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "Col"
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    nt.links.new(tex.outputs["Color"], mix.inputs[6])
    nt.links.new(vc.outputs["Color"], mix.inputs[7])
    nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    if clip is not None:
        gt = nt.nodes.new("ShaderNodeMath")
        gt.operation = "GREATER_THAN"
        gt.inputs[1].default_value = clip
        nt.links.new(tex.outputs["Alpha"], gt.inputs[0])
        nt.links.new(gt.outputs[0], bsdf.inputs["Alpha"])
    if blend == "alpha":
        m.blend_method = "BLEND"
        m.oag_blend = "alpha"
        nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    if blend == "additive":
        m.blend_method = "BLEND"
        m.oag_blend = "additive"
    m["bake_albedo"] = ALBEDO[kind]
    MATS[key] = m
    return m


ART = []


def mesh_object(name, verts, faces, uvs, mat, shadow, layer=0, facing=None):
    """`uvs`: one (u, v) per face corner, Blender's v up. `facing`: the way the first face
    should point; the whole mesh is flipped when it points away (the bake lights the front)."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    uv = me.uv_layers.new(name="UVMap")
    uv.uv.foreach_set("vector", [c for t in uvs for c in t])
    if facing is not None and me.polygons[0].normal.dot(facing) < 0:
        me.flip_normals()
    col = me.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
    me.color_attributes.active_color = col
    me.materials.append(mat)
    me.validate()
    obj = bpy.data.objects.new(name, me)
    sc.collection.objects.link(obj)
    obj.oag_shadow = shadow
    obj.oag_layer = layer
    ART.append(obj)
    return obj


def strip(rows, us, vs):
    """Quads over a grid of rows x columns: faces and per-corner UVs."""
    faces, uvs = [], []
    cols = len(rows[0])
    for i in range(len(rows) - 1):
        for k in range(cols - 1):
            a, b2, c, d = i * cols + k, i * cols + k + 1, (i + 1) * cols + k + 1, (i + 1) * cols + k
            faces.append((a, b2, c, d))
            uvs += [(us[i], vs[k]), (us[i], vs[k + 1]), (us[i + 1], vs[k + 1]), (us[i + 1], vs[k])]
    return [v for r in rows for v in r], faces, uvs


# Road: the floor's own edges, six strips across for the bake, tiled square along.
ACROSS = 6
road_rows, road_u = [], []
for i in range(N + 1):
    j = i % N
    road_rows.append([pos[j] + lat[j] * (-HALF_WIDTH + 2 * HALF_WIDTH * k / ACROSS) for k in range(ACROSS + 1)])
    road_u.append(dist[i] / (2 * HALF_WIDTH))
v, f, uv = strip(road_rows, road_u, [k / ACROSS for k in range(ACROSS + 1)])
road = material("road", host("_surface6_1.tga", GENERIC), "road")
mesh_object("road", v, f, uv, road, "receive", facing=up[0])

# Walls: the inner face (both sides drawn) and a cap, on each edge.
wall = material("wall", host("_wall6_1.tga", GENERIC), "wall", culled=False)
cap = material("walltop", host("_walltop6_1.tga", GENERIC), "wall")
for side, s in (("left", -1), ("right", 1)):
    rows, caps = [], []
    for i in range(N + 1):
        j = i % N
        e = pos[j] + lat[j] * (s * HALF_WIDTH)
        rows.append([e, e + up[j] * (WALL_HEIGHT / 2), e + up[j] * WALL_HEIGHT])
        t = e + up[j] * WALL_HEIGHT
        caps.append([t, t + lat[j] * (s * 1.5)])
    us = [d / WALL_HEIGHT / 2 for d in dist]
    v, f, uv = strip(rows, us, [0.0, 0.5, 1.0])
    mesh_object(f"wall {side}", v, f, uv, wall, "both", facing=lat[0] * -s)
    v, f, uv = strip(caps, [d / 30 for d in dist], [0.0, 1.0])
    mesh_object(f"wall cap {side}", v, f, uv, cap, "both", facing=up[0])

# Terrain: a heightfield either side, pulled to just under the road near the line.
samples = []
for i in range(N):
    for t in range(4):
        samples.append(pos[i].lerp(pos[(i + 1) % N], t / 4))


def near(x, y):
    best, h = 1e18, 0.0
    for s in samples:
        d = (s.x - x) ** 2 + (s.y - y) ** 2
        if d < best:
            best, h = d, s.z
    return math.sqrt(best), h


def hills(x, y):
    r = math.hypot(x / 1.4, y)
    return (
        55 * math.sin(x / 430 + 0.6)
        + 40 * math.cos(y / 370 - 0.3)
        + 25 * math.sin((x + y) / 240)
        + 30
        + max(0.0, r - 1150) * 0.32
    )


def ground(x, y):
    d, h = near(x, y)
    low = h - 3.0
    if d < 44:
        return low
    t = min(1.0, (d - 44) / 150)
    t = t * t * (3 - 2 * t)
    return low + (hills(x, y) - low) * t


# The lake: the spot inside the loop farthest from the line, a basin carved under a water disc.
best_c, best_d = None, 0.0
for gx in range(-900, 901, 50):
    for gy in range(-600, 601, 50):
        d, _ = near(gx, gy)
        if d > best_d:
            best_c, best_d = (gx, gy), d
LAKE = Vector((best_c[0], best_c[1], 0.0))
LAKE_R = min(420.0, (best_d - 110) / 1.3)
LAKE_Z = hills(LAKE.x, LAKE.y) - 14.0
print(f"lake at {tuple(round(c) for c in LAKE.xy)} radius {LAKE_R:.0f} (line {best_d:.0f} away)")
_dry_ground = ground


def ground(x, y):
    g = _dry_ground(x, y)
    d = math.hypot(x - LAKE.x, y - LAKE.y)
    if d >= LAKE_R * 1.3:
        return g
    floor = LAKE_Z - 22.0
    if d <= LAKE_R:
        return floor
    t = (d - LAKE_R) / (LAKE_R * 0.3)
    t = t * t * (3 - 2 * t)
    return floor + (max(g, LAKE_Z + 6.0) - floor) * t


CELL = 40.0
X0, X1, Y0, Y1 = -2600.0, 2600.0, -1900.0, 1900.0
nx, ny = int((X1 - X0) / CELL), int((Y1 - Y0) / CELL)
t0 = time.time()
rows = [[Vector((X0 + i * CELL, Y0 + k * CELL, 0.0)) for k in range(ny + 1)] for i in range(nx + 1)]
for r in rows:
    for p in r:
        p.z = ground(p.x, p.y)
print(f"terrain {nx}x{ny} cells in {time.time() - t0:.0f}s")
v, f, _ = strip(rows, [0] * (nx + 1), [0] * (ny + 1))
uv = [(v[vi].x / 70.0, v[vi].y / 70.0) for face in f for vi in face]
grass = material("grass", host("Grass.tga"), "terrain")
mesh_object("terrain", v, f, uv, grass, "receive", facing=UP)

# Rocks and trees, off the line.
rng = random.Random(3)


def spot(dmin, dmax):
    while True:
        x, y = rng.uniform(X0 + 300, X1 - 300), rng.uniform(Y0 + 300, Y1 - 300)
        d, _ = near(x, y)
        if dmin <= d <= dmax:
            return x, y


rock = material("rock", host("SeaRock.tga"), "rock")
for n in range(18):
    x, y = spot(80, 600)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0)
    ob = ctx.active_object
    s = rng.uniform(14, 34)
    ob.scale = (s * rng.uniform(0.8, 1.5), s * rng.uniform(0.8, 1.5), s * rng.uniform(0.5, 0.9))
    ob.rotation_euler = (0, 0, rng.uniform(0, math.tau))
    ob.location = (x, y, ground(x, y) + s * 0.15)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    me = ob.data
    uvl = me.uv_layers[0] if me.uv_layers else me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co - Vector((x, y, 0))
            uvl.data[li].uv = ((math.atan2(co.y, co.x) / math.tau) * 3, co.z / 30.0)
    col = me.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
    me.color_attributes.active_color = col
    me.materials.append(rock)
    ob.name = f"rock {n:02}"
    ob.oag_shadow = "both"
    ART.append(ob)

# The PSP's texel alpha tops out at 0x80, so a 0.5 clip would cut every leaf.
tree = material("tree", host("Tree1low.tga"), "tree", clip=0.25, culled=False)
for n in range(120):
    x, y = spot(95, 1100)
    if math.hypot(x - LAKE.x, y - LAKE.y) < LAKE_R * 1.15:
        continue
    h = rng.uniform(60, 95)
    w = h * 0.62
    z = ground(x, y) - 2
    a0 = rng.uniform(0, math.pi)
    verts, faces, uvs = [], [], []
    for q in range(2):
        a = a0 + q * math.pi / 2
        dx, dy = math.cos(a) * w / 2, math.sin(a) * w / 2
        k = len(verts)
        verts += [(x - dx, y - dy, z), (x + dx, y + dy, z), (x + dx, y + dy, z + h), (x - dx, y - dy, z + h)]
        faces.append((k, k + 1, k + 2, k + 3))
        uvs += [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    mesh_object(f"tree {n:02}", verts, faces, uvs, tree, "both")


# Bushes, low and many, nearer the line than the trees.
bush = material("bush", host("Bush.tga"), "tree", clip=0.25, culled=False)
for n in range(70):
    x, y = spot(70, 500)
    if math.hypot(x - LAKE.x, y - LAKE.y) < LAKE_R * 1.1:
        continue
    h = rng.uniform(14, 24)
    w = h * 1.3
    z = ground(x, y) - 1
    a0 = rng.uniform(0, math.pi)
    verts, faces, uvs = [], [], []
    for q in range(2):
        a = a0 + q * math.pi / 2
        dx, dy = math.cos(a) * w / 2, math.sin(a) * w / 2
        k = len(verts)
        verts += [(x - dx, y - dy, z), (x + dx, y + dy, z), (x + dx, y + dy, z + h), (x - dx, y - dy, z + h)]
        faces.append((k, k + 1, k + 2, k + 3))
        uvs += [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    mesh_object(f"bush {n:02}", verts, faces, uvs, bush, "both")

# The lake's water: a disc a little past the shore, 03_Track's own sea texture.
water = material("water", host("NewSeaTest.tga"), "water")
RING, SEG = 6, 48
wv = [LAKE + Vector((0, 0, LAKE_Z))]
for r in range(1, RING + 1):
    rad = LAKE_R * 1.22 * r / RING
    for k in range(SEG):
        a = math.tau * k / SEG
        wv.append(LAKE + Vector((math.cos(a) * rad, math.sin(a) * rad, LAKE_Z)))
wf = []
for k in range(SEG):
    wf.append((0, 1 + k, 1 + (k + 1) % SEG))
for r in range(1, RING):
    b0, b1 = 1 + (r - 1) * SEG, 1 + r * SEG
    for k in range(SEG):
        k1 = (k + 1) % SEG
        wf.append((b0 + k, b1 + k, b1 + k1, b0 + k1))
wuv = [((wv[vi].x - LAKE.x) / 90.0, (wv[vi].y - LAKE.y) / 90.0) for face in wf for vi in face]
mesh_object("lake", wv, wf, wuv, water, "receive", facing=UP)

# Mountains: a range all round past the terrain's edge, ridged noise rising from the terrain's own
# rim height, grass on the low slopes, rock above, snow on the peaks (chosen, not measured).
from mathutils import noise

RIM_X, RIM_Y = X1, Y1
RINGS, SEGS = 44, 168
R_IN, R_OUT = 1800.0, 8000.0


def clamp_rim(x, y):
    return max(-RIM_X, min(RIM_X, x)), max(-RIM_Y, min(RIM_Y, y))


def ridge(x, y):
    return noise.ridged_multi_fractal(Vector((x / 2100.0, y / 2100.0, 0.37)), 0.85, 2.0, 6, 1.0, 2.2,
                                      noise_basis="PERLIN_ORIGINAL")


radii = [R_IN + (R_OUT - R_IN) * (k / RINGS) ** 1.35 for k in range(RINGS + 1)]
grid, raw = [], []
for r in radii:
    row = []
    for k in range(SEGS):
        a = math.tau * k / SEGS
        x, y = math.cos(a) * r * 1.25, math.sin(a) * r
        row.append([x, y])
        raw.append(ridge(x, y))
    grid.append(row)
raw_sorted = sorted(raw)
lo, hi = raw_sorted[len(raw) // 20], raw_sorted[-len(raw) // 50]
PEAK = 1000.0
mv, inside = [], []
for row in grid:
    for x, y in row:
        cx, cy = clamp_rim(x, y)
        out_d = math.hypot(x - cx, y - cy)
        if out_d == 0.0:
            mv.append(Vector((x, y, ground(x, y) - 40.0)))
            inside.append(True)
            continue
        h = max(0.0, min(1.0, (ridge(x, y) - lo) / (hi - lo)))
        t = min(1.0, out_d / 2600.0)
        t = t * t * (3 - 2 * t)
        mv.append(Vector((x, y, ground(cx, cy) + t * (h ** 1.6) * PEAK + t * 60.0)))
        inside.append(False)
bands = {"grass": ([], []), "rock": ([], []), "snow": ([], [])}
outer_z = sorted(v.z for v, ins in zip(mv, inside) if not ins)
SNOW_Z = outer_z[int(len(outer_z) * 0.9)]
ROCK_Z = outer_z[int(len(outer_z) * 0.45)]
for i in range(RINGS):
    for k in range(SEGS):
        k1 = (k + 1) % SEGS
        q = (i * SEGS + k, i * SEGS + k1, (i + 1) * SEGS + k1, (i + 1) * SEGS + k)
        if all(inside[v] for v in q):
            continue
        z = sum(mv[v].z for v in q) / 4
        a, b2, c = mv[q[0]], mv[q[1]], mv[q[3]]
        n = (b2 - a).cross(c - a)
        steep = n.length > 0 and abs(n.normalized().z) < 0.72
        band = "snow" if z > SNOW_Z else ("rock" if (z > ROCK_Z or steep) else "grass")
        verts, faces = bands[band]
        base = len(verts)
        verts.extend(mv[v] for v in q)
        faces.append((base, base + 1, base + 2, base + 3))
mats = {
    "grass": material("mountain grass", host("Grass.tga"), "terrain"),
    "rock": material("mountain rock", host("SeaRock.tga"), "rock"),
    "snow": material("mountain snow", host("whitenonalpha.tga", "Data\\Pads\\Textures\\"), "snow"),
}
for band, (verts, faces) in bands.items():
    if not faces:
        continue
    tile = 70.0 if band == "grass" else 180.0
    uvs = [((verts[vi].x + verts[vi].z * 0.5) / tile, (verts[vi].y + verts[vi].z * 0.5) / tile) for f in faces for vi in f]
    mesh_object(f"mountains {band}", verts, faces, uvs, mats[band], "both", facing=UP)
    print(f"mountains {band}: {len(faces)} quads")

# Air traffic: three airships holding station over the valley (static: keyframed motion is
# not built yet, ADR-0076 decision 10).
ship_mat = material("airship", host("Airship.tga"), "roof")
for n, (cx, cy, cz, heading, length) in enumerate(
    ((-600, 900, 420, 0.4, 160), (1500, -200, 520, 2.1, 210), (-1800, -1200, 380, 4.0, 130))
):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1.0)
    ob = ctx.active_object
    ob.scale = (length / 2, length / 7, length / 7)
    ob.rotation_euler = (0, 0, heading)
    ob.location = (cx, cy, cz)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    me = ob.data
    uvl = me.uv_layers[0] if me.uv_layers else me.uv_layers.new(name="UVMap")
    fwd = Vector((math.cos(heading), math.sin(heading), 0))
    for poly in me.polygons:
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co - Vector((cx, cy, cz))
            along = co.dot(fwd) / length + 0.5
            side = Vector((-fwd.y, fwd.x, 0))
            ang = math.atan2(co.z, co.dot(side)) / math.tau + 0.5
            uvl.data[li].uv = (along, ang)
    col = me.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
    me.color_attributes.active_color = col
    me.materials.append(ship_mat)
    ob.name = f"airship {n}"
    ob.oag_shadow = "none"
    ART.append(ob)

# The covered bend: a roof slab over the line on pillars outside the walls.
roof = material("roof", host("_pod2_ceiling.tga"), "roof")
roof_top = material("roof top", host("Metalbase1.tga"), "roof")
idx = list(COVER)
rows_top, rows_under = [], []
for i in idx:
    centre = pos[i] + up[i] * ROOF_HEIGHT
    rows_under.append([centre + lat[i] * (-PILLAR_OFFSET - 8), centre + lat[i] * (PILLAR_OFFSET + 8)])
    rows_top.append([p + up[i] * 6 for p in rows_under[-1]])
us = [(dist[i] - dist[idx[0]]) / 40 for i in idx]
v1, f1, uv1 = strip(rows_under, us, [0.0, 2.6])
v2, f2, uv2 = strip(rows_top, us, [0.0, 2.6])
under = mesh_object("cover roof", v1, f1, uv1, roof, "both", facing=-UP)
top = mesh_object("cover roof top", v2, f2, uv2, roof_top, "both", facing=UP)
pillar = material("pillar", host("_wall6_1.tga", GENERIC), "wall", culled=False)
pv, pf, pu = [], [], []
for i in idx[::2]:
    for s in (-1, 1):
        base = pos[i] + lat[i] * (s * PILLAR_OFFSET)
        bottom = ground(base.x, base.y) - 4
        topz = (pos[i] + up[i] * ROOF_HEIGHT).z
        for a in range(4):
            ang0, ang1 = a * math.pi / 2 + math.pi / 4, (a + 1) * math.pi / 2 + math.pi / 4
            o0 = Vector((math.cos(ang0), math.sin(ang0), 0)) * 5
            o1 = Vector((math.cos(ang1), math.sin(ang1), 0)) * 5
            kk = len(pv)
            pv += [
                Vector((base.x, base.y, bottom)) + o0,
                Vector((base.x, base.y, bottom)) + o1,
                Vector((base.x, base.y, topz)) + o1,
                Vector((base.x, base.y, topz)) + o0,
            ]
            pf.append((kk, kk + 1, kk + 2, kk + 3))
            pu += [(0, 0), (1, 0), (1, (topz - bottom) / 15), (0, (topz - bottom) / 15)]
mesh_object("cover pillars", pv, pf, pu, pillar, "both")

# Painted chevrons before the bends: own PNG, alpha blended, layer 1, a little above the road.
chev = material("chevron", own("hillside_chevron.png", 64, chevron_pixel), "decal", blend="alpha")
for n, i in enumerate((52, 78, 108, 142)):
    rows = []
    for t in range(3):
        j = i + t
        rows.append([pos[j] + up[j] * 0.3 + lat[j] * (-HALF_WIDTH * 0.8 + HALF_WIDTH * 1.6 * c / 2) for c in range(3)])
    v, f, uv = strip(rows, [0.0, 0.5, 1.0], [0.0, 0.5, 1.0])
    mesh_object(f"chevrons {n}", v, f, uv, chev, "receive", layer=1, facing=up[i])


# The start: a gantry over the lap line (spline point 0), the laser line under it, and the grid
# painted where the race lays its eight slots (oag_gameplay::spawn::grid_pose: rows 19.8 apart
# back from the start slot, odd slots 20 to the left).
def box(name, centre, x_axis, y_axis, z_axis, size, mat, shadow="both", tile=20.0):
    hx, hy, hz = (c / 2 for c in size)
    corners = []
    for sx, sy, sz in ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)):
        corners.append(centre + x_axis * (sx * hx) + y_axis * (sy * hy) + z_axis * (sz * hz))
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    uvs = []
    for f in faces:
        a, b2 = corners[f[0]], corners[f[1]]
        wide = (b2 - a).length / tile
        tall = (corners[f[3]] - a).length / tile
        uvs += [(0.0, 0.0), (wide, 0.0), (wide, tall), (0.0, tall)]
    return mesh_object(name, corners, faces, uvs, mat, shadow)


start_ob = next(o for o in sc.objects if o.get("oag_kind") == "start")
sm = start_ob.matrix_world
s_right, s_fwd, s_up, s_pos = (Vector(sm.col[k][:3]) for k in range(4))
s_left = -s_right.normalized()
s_fwd.normalize()
s_up.normalize()

tower = material("gantry tower", host("startline_tower2.tga", GENERIC), "wall", culled=False)
beam = material("gantry beam", host("Metalbase1.tga"), "roof")
board = material("gantry board", host("billboard8.tga", GENERIC), "wall", culled=False)
GANTRY_H = 42.0
g_pos, g_lat, g_up = pos[0], lat[0].normalized(), up[0].normalized()
g_fwd = g_up.cross(g_lat).normalized()
if g_fwd.dot((pos[1] - pos[0])) < 0:
    g_fwd = -g_fwd
for side in (-1, 1):
    base = g_pos + g_lat * (side * (HALF_WIDTH + 7.0))
    box(f"gantry tower {side:+d}", base + g_up * (GANTRY_H / 2 - 4), g_lat, g_fwd, g_up, (8.0, 8.0, GANTRY_H + 8), tower, tile=16.0)
box("gantry beam", g_pos + g_up * GANTRY_H, g_lat, g_fwd, g_up, (2 * HALF_WIDTH + 24.0, 7.0, 9.0), beam)
# The board faces the oncoming craft, on the beam's near side.
bw, bh = 2 * HALF_WIDTH - 6.0, 11.0
bc = g_pos + g_up * (GANTRY_H + 1.0) - g_fwd * 3.8
bv = [bc - g_lat * (bw / 2) - g_up * (bh / 2), bc + g_lat * (bw / 2) - g_up * (bh / 2),
      bc + g_lat * (bw / 2) + g_up * (bh / 2), bc - g_lat * (bw / 2) + g_up * (bh / 2)]
mesh_object("gantry board", bv, [(0, 1, 2, 3)], [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], board, "both", facing=-g_fwd)

laser = material("start laser", host("startline_laser_ADD_GLOW.tga", GENERIC), "decal", blend="additive")
lw = 2.5
lv = [g_pos + g_up * 0.4 + g_lat * (sx * HALF_WIDTH) + g_fwd * (sy * lw) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
mesh_object("start laser", lv, [(0, 1, 2, 3)], [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], laser, "none", layer=2, facing=g_up)


def grid_pixel(x, y):
    """A grid slot: a white frame and a front bar, transparent inside."""
    edge = x < 5 or x > 58 or y < 5 or y > 58
    front = y > 50
    return (235, 235, 235, 210) if (edge or front) else (0, 0, 0, 0)


slot_mat = material("grid slot", own("hillside_grid.png", 64, grid_pixel), "decal", blend="alpha")
for slot in range(1, 9):
    back = 8 - slot
    c = s_pos + s_fwd * (back * 19.8) + s_left * (20.0 if slot % 2 == 1 else 0.0) + s_up * 0.35
    w, l = 7.0, 9.0
    sv = [c - s_left * w - s_fwd * l, c + s_left * w - s_fwd * l, c + s_left * w + s_fwd * l, c - s_left * w + s_fwd * l]
    mesh_object(f"grid slot {slot}", sv, [(0, 1, 2, 3)], [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], slot_mat, "receive", layer=1, facing=s_up)

# Light: a sun casting shadows, a cool fill for the ships (strength 0: it adds nothing to the
# bake), the world colour as the ambient and the bake's sky.
# Where 03_Track's skycube paints its sun (read off a frame aimed at it: format (0.24, 0.31,
# -0.92)), so the baked shadows, the ships' light and the flare agree with the sky.
sun_vec = Vector((0.238, 0.920, 0.312)).normalized()
sun_data = bpy.data.lights.new("sun", "SUN")
sun_data.color = (1.0, 0.9, 0.72)
sun_data.energy = 1.4
sun_data.angle = math.radians(1.5)
sun_data.use_shadow = True
sun = bpy.data.objects.new("sun", sun_data)
sc.collection.objects.link(sun)
sun.rotation_mode = "QUATERNION"
sun.rotation_quaternion = sun_vec.to_track_quat("Z", "Y")
sun.oag_intensity = 1.0
sc.oag_sun = sun
fill_data = bpy.data.lights.new("fill", "SUN")
fill_data.color = (0.42, 0.5, 0.68)
fill_data.energy = 0.0
fill = bpy.data.objects.new("fill", fill_data)
sc.collection.objects.link(fill)
fill.rotation_mode = "QUATERNION"
fill.rotation_quaternion = Vector((0.6, -0.5, 0.35)).normalized().to_track_quat("Z", "Y")
fill.oag_intensity = 0.6
world = bpy.data.worlds.new("World")
sc.world = world
world.use_nodes = True
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs[0].default_value = (0.15, 0.18, 0.24, 1.0)
bg.inputs[1].default_value = 1.0
sc.oag_sky = HOST
sc.oag_lensflare = True
sc.oag_lensflare_atlas = own("hillside_flare.png", 64, flare_pixel)

# The bake: sun, sky and bounce, light only (no albedo), into each art mesh's colour attribute.
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = SAMPLES
sc.cycles.max_bounces = 4
sc.render.bake.target = "VERTEX_COLORS"
real, bake_mats = {}, {}
for ob in ART:
    m = ob.material_slots[0].material
    real[ob.name] = m
    if m.name not in bake_mats:
        bm = bpy.data.materials.new(f"bake {m.name}")
        bm.use_nodes = True
        bsdf = next(n for n in bm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        bsdf.inputs["Base Color"].default_value = (*m["bake_albedo"], 1.0)
        bsdf.inputs["Roughness"].default_value = 1.0
        if m.name == "tree":
            bsdf.inputs["Alpha"].default_value = 0.45  # leaves let light through (no texels here)
        bake_mats[m.name] = bm
    ob.material_slots[0].material = bake_mats[m.name]
# Collision is tagged and never drawn in a race with art, but Cycles would render it: the
# floor lies in the road's plane and would shadow it.
for ob in sc.objects:
    if ob.get("oag_kind") in ("floor", "wall"):
        ob.hide_render = True
bpy.ops.object.select_all(action="DESELECT")
for ob in ART:
    ob.select_set(True)
ctx.view_layer.objects.active = ART[0]
t0 = time.time()
assert bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, target="VERTEX_COLORS") == {"FINISHED"}
print(f"baked {len(ART)} meshes at {SAMPLES} samples in {time.time() - t0:.0f}s")
# Exposure (chosen): brings the road's median into 03_Track's own COLOR_0 range for the same
# texture (_surface6_1 draws at about 0.23 to 0.55 linear there).
EXPOSURE = 1.35
for ob in ART:
    ob.material_slots[0].material = real[ob.name]
    data = ob.data.color_attributes["Col"].data
    for c in data:
        r, g, b, a = c.color
        c.color = (min(1.0, r * EXPOSURE), min(1.0, g * EXPOSURE), min(1.0, b * EXPOSURE), a)

# Report: the light under the line and the bake's density.
for ob in ART:
    if ob.name in ("road", "terrain", "cover roof"):
        cols = [c.color for c in ob.data.color_attributes["Col"].data]
        lum = sorted(0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2] for c in cols)
        area = sum(p.area for p in ob.data.polygons)
        print(
            f"{ob.name}: {len(ob.data.vertices)} vertices over {area:.0f} square units "
            f"({len(ob.data.vertices) / area * 1000:.2f} per 1000), linear luminance "
            f"p5 {lum[len(lum) // 20]:.3f} median {lum[len(lum) // 2]:.3f} p95 {lum[-len(lum) // 20]:.3f}"
        )

manifest = os.path.join(out, "hillside.track.toml")
track = scene.write_track(ctx, manifest)
covered = [i for i, q in enumerate(track.paths[0].points) if q.light_scale != (255, 255, 255, 255)]
print(
    f"wrote {manifest}: {len(track.paths[0].points)} points, {len(track.nodes)} nodes, "
    f"{len(track.art.meshes)} art meshes, {len(track.art.textures)} textures; "
    f"light scale lowered at points {covered}"
)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "hillside.blend"))
