"""Headless: Checkpoint Circuit, a stadium loop with a pit lane, built with the OAG add-on for
the checkpoint-circuit mod. Pulse's generic road and wall textures, 03_Track's grass and its sky
are named (host references; no pixels leave the disc).

The pit lane is a real fork in the spline: three paths and two junctions, the pattern Pulse's own
forked circuits use (05_Track, 07_Track: the primary and the alternate leave one junction and
meet at the next). Path 0 is the main straight beside the pit, path 1 the pit lane, path 2 the
rest of the lap. So the AI can drive the pit lane as a route.

Simulation mod properties (`mod_*`, read by the guest in guest/src/lib.rs):
- four checkpoint triggers, `oag/triggers/checkpoint <n>`, `mod_checkpoint = n` (1 to 4 in lap
  order), each a gate across the whole road;
- the pit trigger, `oag/triggers/pit`, `mod_pit = 1`, over the pit lane alone;
- the pit lane's spline path, `mod_pit = 1`, so a module finds its route.

Everything here is chosen, not measured. Rebuild into tracks/ with Blender 4.2+:

    blender -b --factory-startup --python-exit-code 1 --python checkpoint_circuit.py -- tracks [--samples N]

OAG_ADDON_DIR names the add-on's parent directory (default: the engine checkout this repo is
mounted in as assets/mods/examples, i.e. ../../../../scripts/blender from here).
"""

import json
import math
import os
import sys
import time

ADDON = os.environ.get(
    "OAG_ADDON_DIR",
    os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "scripts", "blender")),
)
sys.path.insert(0, ADDON)
import bpy
from mathutils import Vector

import oag_track
from oag_track import derive, f32, scene
from oag_track.model import Path, SplinePoint

args = sys.argv[sys.argv.index("--") + 1 :]
out = args[0]
SAMPLES = int(args[args.index("--samples") + 1]) if "--samples" in args else 32
os.makedirs(out, exist_ok=True)

HOST = "Data\\Environments\\03_Track\\track.vex"
TEX = "Data\\Environments\\03_Track\\Textures\\"
GENERIC = "Data\\Environments\\GenericTrackTextures\\"

# The loop, Blender's x/y: two straights 1,800 long joined by half circles of radius 450.
STRAIGHT = 900.0
RADIUS = 450.0
SPACING = 20.0
HALF_WIDTH = 28.0
WALL_HEIGHT = 5.0
# The pit lane: leaves the main straight at x = SPLIT_X, rejoins at MERGE_X, runs PIT_OFFSET to
# the outside (Blender -y) between them, easing in and out over EASE.
SPLIT_X, MERGE_X = -700.0, 700.0
PIT_OFFSET = 80.0
PIT_HALF_WIDTH = 18.0
EASE = 250.0
DIVIDER = 45.0  # the wall between the main road and the pit lane, from the main line
LAP_LINE = Vector((0.0, 2 * RADIUS, 0.0))  # mid back straight

ALBEDO = {
    "road": (0.30, 0.30, 0.31),
    "pit": (0.28, 0.30, 0.36),
    "wall": (0.45, 0.45, 0.45),
    "terrain": (0.20, 0.30, 0.12),
    "gate": (0.40, 0.40, 0.42),
}


def loop_polyline():
    """The closed centre line, dense, Blender's axes, from (-STRAIGHT, 0) heading +x."""
    pts = []
    for k in range(180):
        pts.append(Vector((-STRAIGHT + 2 * STRAIGHT * k / 180, 0.0, 0.0)))
    for k in range(90):
        a = -math.pi / 2 + math.pi * k / 90
        pts.append(Vector((STRAIGHT + RADIUS * math.cos(a), RADIUS + RADIUS * math.sin(a), 0.0)))
    for k in range(180):
        pts.append(Vector((STRAIGHT - 2 * STRAIGHT * k / 180, 2 * RADIUS, 0.0)))
    for k in range(90):
        a = math.pi / 2 + math.pi * k / 90
        pts.append(Vector((-STRAIGHT + RADIUS * math.cos(a), RADIUS + RADIUS * math.sin(a), 0.0)))
    return pts


def smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def pit_offset(x):
    """How far the pit lane's centre is outside the main line at `x` (0 outside the fork)."""
    if x <= SPLIT_X or x >= MERGE_X:
        return 0.0
    return PIT_OFFSET * min(smooth((x - SPLIT_X) / EASE), smooth((MERGE_X - x) / EASE))


def resample_open(points, count):
    """`count` points evenly spaced by arc length along an open polyline, both ends kept."""
    gaps = [math.dist(points[i], points[i + 1]) for i in range(len(points) - 1)]
    total = sum(gaps)
    out_pts, seg, run = [], 0, 0.0
    for k in range(count):
        want = total * k / (count - 1)
        while seg < len(gaps) - 1 and run + gaps[seg] <= want:
            run += gaps[seg]
            seg += 1
        t = 0.0 if gaps[seg] == 0.0 else min(1.0, (want - run) / gaps[seg])
        a, b = points[seg], points[seg + 1]
        out_pts.append(tuple(f32.r(a[i] + (b[i] - a[i]) * t) for i in range(3)))
    out_pts[0], out_pts[-1] = tuple(points[0]), tuple(points[-1])
    return out_pts


bpy.ops.wm.read_factory_settings(use_empty=True)
oag_track.register()
ctx = bpy.context
sc = ctx.scene
sc.oag_track_id = "checkpoint-circuit"
sc.oag_track_title = "Checkpoint Circuit"
sc.oag_track_host = "wipeout-pulse"
sc.oag_track_notes = (
    "a stadium loop with a pit lane forking off the main straight (three paths, two junctions); "
    "four checkpoint gates and a pit trigger for the checkpoint-circuit mod (chosen, not measured)"
)

# The ring: the add-on's own closed-loop maths, in the format's axes.
ring_fmt = [scene.to_format(tuple(p)) for p in loop_polyline()]
length = sum(math.dist(ring_fmt[i], ring_fmt[(i + 1) % len(ring_fmt)]) for i in range(len(ring_fmt)))
N = round(length / SPACING)
loop = derive.build_path(derive.resample_closed(ring_fmt, N), HALF_WIDTH).points


def nearest(v):
    target = scene.to_format(tuple(v))
    return min(range(N), key=lambda i: sum((loop[i].pos[c] - target[c]) ** 2 for c in range(3)))


s = nearest(Vector((SPLIT_X, 0.0, 0.0)))
m = nearest(Vector((MERGE_X, 0.0, 0.0)))
assert s < m, (s, m)
xs, xm = loop[s].pos[0], loop[m].pos[0]


def open_spacing(points):
    return max(f32.dist(points[i].pos, points[i + 1].pos) for i in range(len(points) - 1))


# Path 0: the main straight beside the pit (both junction points); path 2: the rest of the lap.
main = loop[s : m + 1]
rest = [loop[i % N] for i in range(m + 1, s + N)]

# Path 1: the pit lane, from the split point to the merge point. Its offset is along the main
# line's lateral (+lateral is Blender -y on this straight).
lat = loop[s].lateral
dense = []
for k in range(2001):
    x = xs + (xm - xs) * k / 2000
    q = pit_offset(x)
    dense.append((x, loop[s].pos[1], loop[s].pos[2] + lat[2] * q))
dense[0], dense[-1] = loop[s].pos, loop[m].pos
pit_len = sum(math.dist(dense[i], dense[i + 1]) for i in range(len(dense) - 1))
pit_pos = resample_open(dense, round(pit_len / SPACING) + 1)
pit_bound = f32.r(PIT_HALF_WIDTH * derive.AI_FRACTION)
pit = []
for i, p in enumerate(pit_pos):
    before = pit_pos[i - 1] if i > 0 else loop[s - 1].pos
    after = pit_pos[i + 1] if i + 1 < len(pit_pos) else loop[(m + 1) % N].pos
    forward = f32.unit(f32.sub(after, before))
    lateral = f32.unit(f32.cross(forward, derive.WORLD_UP))
    up = f32.unit(f32.cross(lateral, forward))
    t = (p[0] - xs) / (xm - xs)
    pit.append(
        SplinePoint(
            pos=tuple(f32.r(c) for c in p),
            tangent=forward,
            down=(-up[0], -up[1], -up[2]),
            lateral=lateral,
            progress=f32.r(loop[s].progress + (loop[m].progress - loop[s].progress) * t),
            half_width_left=f32.r(PIT_HALF_WIDTH),
            half_width_right=f32.r(PIT_HALF_WIDTH),
            ai_bound_left=-pit_bound,
            ai_bound_right=pit_bound,
            racing_line=0.0,
            section_id=0xFF,
            flags=0,
            light_scale=(255, 255, 255, 255),
        )
    )
# The two junction points are the main line's own, bit for bit, as on the disc's forks.
pit[0], pit[-1] = main[0], main[-1]

paths = [
    Path(main, open_spacing(main), entry=1, exit=0),
    Path(pit, open_spacing(pit), entry=1, exit=0),
    Path(rest, open_spacing(rest), entry=0, exit=1),
]
spline_objs = [scene.make_spline_object(sc, p, i) for i, p in enumerate(paths)]
spline_objs[1]["mod_pit"] = 1
sc["oag_junctions"] = json.dumps([{"prev": [0, 1], "next": [2, -1]}, {"prev": [2, -1], "next": [0, 1]}])

# The start: the lap line mid back straight, the grid laid behind it.
L = nearest(LAP_LINE)
scene.make_start_object(ctx, derive.start_frame([loop[(L + i) % N] for i in range(N)]))

# Pads on the ring, snapped to the nearest point (Blender x/y). Chosen, not measured.
for index, (kind, at) in enumerate(
    (("speedup", (-450, 900)), ("speedup", (1200, 100)))
):
    scene.make_pad_object(ctx, derive.pad_at(loop[nearest(Vector((*at, 0)))], kind), kind, index)
for index, at in enumerate(((-1250, 150), (300, 900), (1250, 780))):
    scene.make_pad_object(ctx, derive.pad_at(loop[nearest(Vector((*at, 0)))], "weapon"), "weapon", index)

# Collision: one floor over the ring, widened over the pit lane where it runs beside the main
# road, the ring's two walls (the outer one following the pit lane's edge), and a divider.
P = [Vector(scene.to_blender(q.pos)) for q in loop]
LAT = [Vector(scene.to_blender(q.lateral)) for q in loop]
UP = Vector((0.0, 0.0, 1.0))


def outer(i):
    """The floor's +lateral edge at ring point i."""
    if s <= i <= m:
        return max(HALF_WIDTH, pit_offset(P[i].x) + PIT_HALF_WIDTH)
    return HALF_WIDTH


def fmt(v):
    return tuple(f32.r(c) for c in scene.to_format(tuple(v)))


def quad_strip(a_rows, b_rows, closed):
    """Triangles between two rows of points, wound as derive.ribbon's floor."""
    verts, tris = [], []
    count = len(a_rows) if closed else len(a_rows) - 1
    for i in range(count):
        j = (i + 1) % len(a_rows)
        k = len(verts)
        verts += [fmt(a_rows[i]), fmt(b_rows[i]), fmt(a_rows[j]), fmt(b_rows[j])]
        tris += [(k, k + 1, k + 2), (k + 1, k + 3, k + 2)]
    return verts, tris


def wall_strip(rows, left, closed):
    """A wall along `rows`, WALL_HEIGHT tall; `left` faces +lateral (a ring's left wall)."""
    verts, tris = [], []
    count = len(rows) if closed else len(rows) - 1
    for i in range(count):
        j = (i + 1) % len(rows)
        a, b = (rows[i], rows[j]) if left else (rows[j], rows[i])
        k = len(verts)
        verts += [fmt(a), fmt(b), fmt(a + UP * WALL_HEIGHT), fmt(b + UP * WALL_HEIGHT)]
        tris += [(k, k + 1, k + 2), (k + 1, k + 3, k + 2)]
    return verts, tris


left_edge = [P[i] - LAT[i] * HALF_WIDTH for i in range(N)]
right_edge = [P[i] + LAT[i] * outer(i) for i in range(N)]
floor_v, floor_t = quad_strip(left_edge, right_edge, True)
wall_v, wall_t = wall_strip(left_edge, True, True)
v, t = wall_strip(right_edge, False, True)
wall_t += [(a + len(wall_v), b + len(wall_v), c + len(wall_v)) for a, b, c in t]
wall_v += v
# The divider: a thin wall where the pit lane runs at its full offset, a face to each side.
div_rows = [P[i] + LAT[i] * DIVIDER for i in range(s, m + 1) if pit_offset(P[i].x) >= PIT_OFFSET - 1e-3]
for side, offset in ((False, -1.0), (True, 1.0)):
    v, t = wall_strip([r + LAT[s] * offset for r in div_rows], side, False)
    wall_t += [(a + len(wall_v), b + len(wall_v), c + len(wall_v)) for a, b, c in t]
    wall_v += v
from oag_track.model import CollisionMesh, CollisionNode  # noqa: E402

for node, (kind, verts, tris) in enumerate((("floor", floor_v, floor_t), ("wall", wall_v, wall_t))):
    mesh = CollisionMesh(verts, tris, [1.0] * len(verts))
    obj = scene.make_collision_object(sc, kind, mesh, CollisionNode(kind, [mesh], kind), node, 0, False)
    obj.name = kind

# Triggers: a box mesh each, turned into a trigger by the add-on's "Make trigger from mesh".
# The gates split the lap into four equal stretches of about 1,600 units: the west bend's
# apex, mid main straight (across the main road and the pit lane), the east bend's apex, and
# the lap line.
PIT_EDGE = PIT_OFFSET + PIT_HALF_WIDTH
TRIGGERS = (
    ("checkpoint 1", (-STRAIGHT - RADIUS, RADIUS), (110, 20), {"checkpoint": 1}),
    ("checkpoint 2", (0, (HALF_WIDTH - PIT_EDGE) / 2), (20, HALF_WIDTH + PIT_EDGE + 20), {"checkpoint": 2}),
    ("checkpoint 3", (STRAIGHT + RADIUS, RADIUS), (110, 20), {"checkpoint": 3}),
    ("checkpoint 4", (LAP_LINE.x, LAP_LINE.y), (20, 110), {"checkpoint": 4}),
    ("pit", (0, -PIT_OFFSET), (2 * (MERGE_X - EASE) - 40, 2 * PIT_HALF_WIDTH + 8), {"pit": 1}),
)
for name, (x, y), (sx, sy), props in TRIGGERS:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, 10.0))
    box = ctx.active_object
    box.name = f"oag/triggers/{name}"
    box.scale = (sx, sy, 30.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.select_all(action="DESELECT")
    box.select_set(True)
    ctx.view_layer.objects.active = box
    assert bpy.ops.oag.trigger_from_mesh() == {"FINISHED"}
    trigger = next(o for o in sc.objects if o.get("oag_kind") == "trigger" and o.get("oag_name") == name)
    for key, value in props.items():
        trigger[f"mod_{key}"] = value
    bpy.data.objects.remove(box)

# Art: the road and pit surface, the walls, gates over the checkpoints, a grass ground.
IMAGES, MATS, ART = {}, {}, []


def host(name, folder=TEX):
    if name not in IMAGES:
        img = bpy.data.images.new(name, 8, 8)
        img["oag_host_entry"] = HOST
        img["oag_host_name"] = folder + name
        IMAGES[name] = img
    return IMAGES[name]


def material(key, image, kind, culled=True):
    if key in MATS:
        return MATS[key]
    mat = bpy.data.materials.new(key)
    mat.use_nodes = True
    mat.use_backface_culling = culled
    nt = mat.node_tree
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
    mat["bake_albedo"] = ALBEDO[kind]
    MATS[key] = mat
    return mat


def mesh_object(name, verts, faces, uvs, mat, shadow, facing=None):
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
    ART.append(obj)
    return obj


def strip(rows, us, vs):
    faces, uvs = [], []
    cols = len(rows[0])
    for i in range(len(rows) - 1):
        for k in range(cols - 1):
            a, b, c, d = i * cols + k, i * cols + k + 1, (i + 1) * cols + k + 1, (i + 1) * cols + k
            faces.append((a, b, c, d))
            uvs += [(us[i], vs[k]), (us[i], vs[k + 1]), (us[i + 1], vs[k + 1]), (us[i + 1], vs[k])]
    return [v for r in rows for v in r], faces, uvs


dist = [0.0]
for i in range(1, N + 1):
    dist.append(dist[-1] + (P[i % N] - P[i - 1]).length)
ACROSS = 6
rows, us = [], []
for i in range(N + 1):
    j = i % N
    rows.append([P[j] + LAT[j] * (-HALF_WIDTH + 2 * HALF_WIDTH * k / ACROSS) for k in range(ACROSS + 1)])
    us.append(dist[i] / (2 * HALF_WIDTH))
v, f, uv = strip(rows, us, [k / ACROSS for k in range(ACROSS + 1)])
mesh_object("road", v, f, uv, material("road", host("_surface6_1.tga", GENERIC), "road"), "receive", facing=UP)

# The pit apron: the floor from the main road's edge out to the pit lane's outer edge.
rows, us = [], []
for i in range(s, m + 1):
    w = outer(i)
    rows.append([P[i] + LAT[i] * (HALF_WIDTH + (w - HALF_WIDTH) * k / 4) for k in range(5)])
    us.append((dist[i] - dist[s]) / (2 * PIT_HALF_WIDTH))
v, f, uv = strip(rows, us, [k / 4 * 2.5 for k in range(5)])
mesh_object("pit apron", v, [tuple(x) for x in f], uv, material("pit", host("_surface6_1.tga", GENERIC), "pit"), "receive", facing=UP)

wall = material("wall", host("_wall6_1.tga", GENERIC), "wall", culled=False)
cap = material("walltop", host("_walltop6_1.tga", GENERIC), "wall")
for name, edge, sgn in (("left", left_edge, -1), ("right", right_edge, 1)):
    rows, caps = [], []
    for i in range(N + 1):
        e = edge[i % N]
        rows.append([e, e + UP * (WALL_HEIGHT / 2), e + UP * WALL_HEIGHT])
        top = e + UP * WALL_HEIGHT
        caps.append([top, top + LAT[i % N] * (sgn * 1.5)])
    v, f, uv = strip(rows, [d / WALL_HEIGHT / 2 for d in dist], [0.0, 0.5, 1.0])
    mesh_object(f"wall {name}", v, f, uv, wall, "both")
    v, f, uv = strip(caps, [d / 30 for d in dist], [0.0, 1.0])
    mesh_object(f"wall cap {name}", v, f, uv, cap, "both", facing=UP)
rows = []
for r in div_rows:
    rows.append([r + UP * 0.0, r + UP * (WALL_HEIGHT / 2), r + UP * WALL_HEIGHT])
dd = [0.0]
for i in range(1, len(div_rows)):
    dd.append(dd[-1] + (div_rows[i] - div_rows[i - 1]).length)
v, f, uv = strip(rows, [d / WALL_HEIGHT / 2 for d in dd], [0.0, 0.5, 1.0])
mesh_object("divider", v, f, uv, wall, "both")

# Gates: two towers and a beam over each checkpoint, so a pilot sees where the timer resets.
tower = material("gate tower", host("startline_tower2.tga", GENERIC), "gate", culled=False)
beam = material("gate beam", host("Metalbase1.tga"), "gate")


def box(name, centre, x_axis, y_axis, z_axis, size, mat, tile=16.0):
    hx, hy, hz = (c / 2 for c in size)
    corners = []
    for sx, sy, sz in ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)):
        corners.append(centre + x_axis * (sx * hx) + y_axis * (sy * hy) + z_axis * (sz * hz))
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    uvs = []
    for fc in faces:
        a, b = corners[fc[0]], corners[fc[1]]
        uvs += [(0.0, 0.0), ((b - a).length / tile, 0.0), ((b - a).length / tile, (corners[fc[3]] - a).length / tile), (0.0, (corners[fc[3]] - a).length / tile)]
    return mesh_object(name, corners, faces, uvs, mat, "both")


GATE_H = 36.0
for name, (x, y), _, props in TRIGGERS:
    if "checkpoint" not in props:
        continue
    i = nearest(Vector((x, y, 0.0)))
    g_lat = LAT[i].normalized()
    g_fwd = UP.cross(g_lat).normalized()
    lo, hi = -HALF_WIDTH - 6.0, outer(i) + 6.0
    for k, off in enumerate((lo, hi)):
        box(f"{name} tower {k}", P[i] + g_lat * off + UP * (GATE_H / 2 - 4), g_lat, g_fwd, UP, (6.0, 6.0, GATE_H + 8), tower)
    box(f"{name} beam", P[i] + g_lat * ((lo + hi) / 2) + UP * GATE_H, g_lat, g_fwd, UP, (hi - lo + 6.0, 5.0, 6.0), beam)

ground = material("grass", host("Grass.tga"), "terrain")
G = 4000.0
gv = [Vector((x, y, -0.5)) for x, y in ((-G, -G), (G, -G), (G, G), (-G, G))]
mesh_object("ground", gv, [(0, 1, 2, 3)], [(0.0, 0.0), (G / 40, 0.0), (G / 40, G / 40), (0.0, G / 40)], ground, "receive", facing=UP)

# Light: a sun casting shadows where 03_Track's skycube paints it (Hillside's), the world colour as
# the ambient, and a Cycles bake of sun and sky into every art mesh's colour attribute.
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
world = bpy.data.worlds.new("World")
sc.world = world
world.use_nodes = True
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs[0].default_value = (0.15, 0.18, 0.24, 1.0)
bg.inputs[1].default_value = 1.0
sc.oag_sky = HOST

sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = SAMPLES
sc.cycles.max_bounces = 3
sc.render.bake.target = "VERTEX_COLORS"
real, bake_mats = {}, {}
for ob in ART:
    mat = ob.material_slots[0].material
    real[ob.name] = mat
    if mat.name not in bake_mats:
        bm = bpy.data.materials.new(f"bake {mat.name}")
        bm.use_nodes = True
        bsdf = next(n for n in bm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        bsdf.inputs["Base Color"].default_value = (*mat["bake_albedo"], 1.0)
        bsdf.inputs["Roughness"].default_value = 1.0
        bake_mats[mat.name] = bm
    ob.material_slots[0].material = bake_mats[mat.name]
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
# Exposure (chosen, Hillside's); the pit apron a cool blue so it reads as the pit lane.
EXPOSURE = 1.35
TINT = {"pit apron": (0.8, 0.9, 1.25)}
for ob in ART:
    ob.material_slots[0].material = real[ob.name]
    tint = TINT.get(ob.name, (1.0, 1.0, 1.0))
    for c in ob.data.color_attributes["Col"].data:
        r, g, b, a = c.color
        c.color = tuple(min(1.0, x * EXPOSURE * k) for x, k in zip((r, g, b), tint)) + (a,)

manifest = os.path.join(out, "checkpoint-circuit.track.toml")
track = scene.write_track(ctx, manifest)
print(
    f"wrote {manifest}: paths {[len(p.points) for p in track.paths]}, split {s}, merge {m}, "
    f"lap line {L}, {len(track.nodes)} nodes, {len(track.triggers)} triggers, "
    f"{len(track.art.meshes)} art meshes"
)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "checkpoint-circuit.blend"))
