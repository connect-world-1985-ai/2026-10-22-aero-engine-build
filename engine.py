# Stylized CFM LEAP-1A high-bypass turbofan, built 100% procedurally with bpy (Blender 4.3.2, Cycles CPU).
#
# Usage:  blender -b -P engine.py -- MODE [VIEW] [key=value ...]
#   MODE  = side | preview | mid | still | setup
#   VIEW  = cut | ext            (ignored by side/setup)
#   keys  : samples=N  tag=NAME  span=DEG (cutaway wedge, default 100)  center=DEG
#
# Reference numbers (public sources, see README.md):
#   EASA TCDS E.110: single-stage fan, 3-stage LPC, 10-stage HPC, annular combustor,
#                    2-stage HPT, 7-stage LPT; length 3328 mm (fan case fwd flange -> TRF aft flange)
#   CFM / Safran   : fan diameter 78 in (1981 mm)
#   Airbus LEAP-1A training manual: 18 fan blades, BPR 11:1, 19 fuel nozzles,
#                    booster 3 rotor + 4 stator rows, HPC IGV + 9 stator rows
# Units: metres. Engine axis = +X, fan case forward flange at x = 0.
import bpy, bmesh, math, sys, os, time
from mathutils import Vector, Matrix

T0 = time.time()
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
pos = [a for a in argv if '=' not in a]
kv = dict(a.split('=', 1) for a in argv if '=' in a)
MODE = pos[0] if pos else 'preview'
VIEW = pos[1] if len(pos) > 1 else 'cut'
OUT = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else '/workspace/2026-10-22-aero-engine-build'
OUT = '/workspace/2026-10-22-aero-engine-build'
TAG = kv.get('tag', '')

# ------------------------------------------------------------------ reference data
LEAP = dict(
    fan_diameter=1.9812,      # 78 in  (CFM, Safran)
    length=3.328,             # EASA TCDS E.110, fan case fwd flange -> TRF aft flange
    fan_blades=18,            # Airbus LEAP-1A training manual
    lpc_stages=3, hpc_stages=10, hpt_stages=2, lpt_stages=7,   # EASA TCDS E.110
    fuel_nozzles=19,          # Airbus LEAP-1A training manual
    bypass_ratio=11.0,        # not geometric; informs the large bypass annulus
)
R_FAN = LEAP['fan_diameter'] / 2

# cutaway wedge: angle measured in the YZ plane, 0 deg = +Y, 90 deg = +Z
CUT_SPAN = math.radians(float(kv.get('span', 110)))
CUT_CENTER = math.radians(float(kv.get('center', 135)))   # top-left as seen from the -Y / front-left camera
PYLON = kv.get('pylon', '0') == '1'                         # P2 pylon stub: built, excluded from renders by default
FAN_FULL = True                                             # keep the whole fan ring (Raymond's decision)
SIDE = (MODE == 'side')
if SIDE:                                                    # half section facing the -Y ortho camera
    CUT_SPAN, CUT_CENTER, FAN_FULL = math.radians(180), math.radians(180), False
SEG = 144                                                   # segments for a full 360 revolve

# ------------------------------------------------------------------ scene reset
bpy.ops.wm.read_factory_settings(use_empty=True)
# the scene that gets rendered must be the context scene (render.render(scene=...) is ignored headless)
if VIEW == 'ext' and MODE not in ('side', 'setup'):
    SC_EXT = bpy.context.scene; SC_EXT.name = 'Exterior'; SC_CUT = bpy.data.scenes.new('Cutaway')
else:
    SC_CUT = bpy.context.scene; SC_CUT.name = 'Cutaway'; SC_EXT = bpy.data.scenes.new('Exterior')

# ------------------------------------------------------------------ helpers (new_mat/link pattern copied from blender-demo/scene.py)
def new_mat(name, color=(0.5, 0.5, 0.5), rough=0.4, metal=0.0, emit=None, estr=0.0, coat=0.0, aniso=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if coat:
        b.inputs['Coat Weight'].default_value = coat
        b.inputs['Coat Roughness'].default_value = 0.08
    if aniso:
        b.inputs['Anisotropic'].default_value = aniso
    if emit is not None:
        b.inputs['Emission Color'].default_value = (*emit, 1)
        b.inputs['Emission Strength'].default_value = estr
    m.diffuse_color = (*color, 1)
    return m

COLLS = {}
def coll(name, parent=None):
    if name in COLLS: return COLLS[name]
    c = bpy.data.collections.new(name)
    (parent.children if parent else bpy.data.collections['Engine'].children if 'Engine' in bpy.data.collections and name != 'Engine' else None)
    COLLS[name] = c
    return c

ROOT = bpy.data.collections.new('Engine'); COLLS['Engine'] = ROOT
def sub(name, parent=ROOT):
    if name in COLLS: return COLLS[name]
    c = bpy.data.collections.new(name); parent.children.link(c); COLLS[name] = c
    return c

STATS = {}
def mesh_obj(name, bm, mats, c, smooth=True, sharp_deg=35):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    for m in mats: me.materials.append(m)
    if smooth:
        for p in me.polygons: p.use_smooth = True
        try: me.set_sharp_from_angle(angle=math.radians(sharp_deg))
        except Exception as e: print('sharp_from_angle failed', e)
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    STATS[name] = len(me.vertices)
    return o

def interp(tab, x):
    if x <= tab[0][0]: return tab[0][1]
    for (x0, y0), (x1, y1) in zip(tab, tab[1:]):
        if x <= x1:
            t = (x - x0) / (x1 - x0) if x1 > x0 else 0
            return y0 + t * (y1 - y0)
    return tab[-1][1]

def in_cut(theta, margin=0.0):
    d = (theta - CUT_CENTER + math.pi) % (2 * math.pi) - math.pi
    return abs(d) < CUT_SPAN / 2 + margin

def kept_angles(full):
    if full:
        n = SEG
        return [2 * math.pi * i / n for i in range(n)], True
    a0 = CUT_CENTER + CUT_SPAN / 2
    span = 2 * math.pi - CUT_SPAN
    n = max(8, int(math.ceil(SEG * span / (2 * math.pi))))
    return [a0 + span * i / n for i in range(n + 1)], False

def revolve(name, prof, mat, cap, c, full=False, seg_scale=1.0):
    """Revolve closed (x, r) polygon about +X. Partial sweeps get ngon caps with material `cap`."""
    global SEG
    s0 = SEG; SEG = max(16, int(SEG * seg_scale))
    angs, wrap = kept_angles(full)
    SEG = s0
    bm = bmesh.new()
    rings = [[bm.verts.new((x, r * math.cos(a), r * math.sin(a))) for (x, r) in prof] for a in angs]
    n = len(prof)
    m = len(rings) if wrap else len(rings) - 1
    for i in range(m):
        A, B = rings[i], rings[(i + 1) % len(rings)]
        for j in range(n):
            try: bm.faces.new((A[j], A[(j + 1) % n], B[(j + 1) % n], B[j]))
            except ValueError: pass
    if not wrap:
        for ring in (rings[0], rings[-1]):
            try:
                f = bm.faces.new(ring); f.material_index = 1
            except ValueError: pass
    return mesh_obj(name, bm, [mat, cap], c)

def shell(pts, t):
    """closed polygon from a polyline (x, r) offset outward by t"""
    return list(pts) + [(x, r + t) for (x, r) in reversed(pts)]

def shell_in(pts, t):
    return list(pts) + [(x, max(0.003, r - t)) for (x, r) in reversed(pts)]

# ------------------------------------------------------------------ blade generator
def airfoil(npts, tc, camber):
    out = []
    for k in range(npts):
        u = 2 * math.pi * k / npts
        s = 0.5 * math.cos(u)                     # -0.5 (TE) .. 0.5 (LE)
        thick = 0.5 * tc * math.sin(u) * (1.0 + 0.35 * math.cos(u))   # fatter toward LE
        t = thick + camber * (1 - 4 * s * s)
        out.append((s, t))
    return out

def blade(bm, x_c, r0, r1, chord, stagger, tc, camber, theta0, nsec=5, npts=12, sweep=None, sign=1):
    """One blade. chord/stagger/tc/camber are callables of span fraction f in [0,1]."""
    secs = []
    for i in range(nsec):
        f = i / (nsec - 1)
        r = r0 + (r1 - r0) * f
        c, b = chord(f), sign * stagger(f)
        dx = sweep(f) if sweep else 0.0
        ring = []
        for s, t in airfoil(npts, tc(f), camber(f)):
            s *= -c; t *= c * sign
            ax = s * math.cos(b) - t * math.sin(b)
            tg = s * math.sin(b) + t * math.cos(b)
            ph = theta0 + tg / r
            ring.append(bm.verts.new((x_c + dx + ax, r * math.cos(ph), r * math.sin(ph))))
        secs.append(ring)
    for A, B in zip(secs, secs[1:]):
        for j in range(npts):
            bm.faces.new((A[j], A[(j + 1) % npts], B[(j + 1) % npts], B[j]))
    bm.faces.new(secs[0]); bm.faces.new(list(reversed(secs[-1])))

def const(v): return lambda f: v
def lin(a, b): return lambda f: a + (b - a) * f

def blade_row(name, c, mat, x, n, r0, r1, chord, stagger, tc, camber, sign=1, nsec=4, npts=12,
              sweep=None, cut=True, phase=0.0):
    bm = bmesh.new(); kept = 0
    for k in range(n):
        th = 2 * math.pi * (k + phase) / n
        if cut and in_cut(th, margin=math.radians(4)):
            continue
        blade(bm, x, r0, r1, chord, stagger, tc, camber, th, nsec, npts, sweep, sign)
        kept += 1
    o = mesh_obj(name, bm, [mat], c, sharp_deg=60)
    return o

def cylinder_between(bm, p0, p1, rad, nv=10):
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    res = bmesh.ops.create_cone(bm, cap_ends=True, segments=nv, radius1=rad, radius2=rad, depth=d.length)
    rot = d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation((p0 + p1) / 2) @ rot, verts=res['verts'])

# ------------------------------------------------------------------ materials (restrained, product-photo palette)
M = dict(
    nacelle=new_mat('Nacelle_Paint', (0.42, 0.425, 0.42), rough=0.30, coat=0.6),
    duct=new_mat('BypassDuct_SatinAlu', (0.62, 0.63, 0.64), rough=0.42, metal=1.0),
    spinner=None,
    fan=new_mat('Fan_Composite', (0.07, 0.075, 0.085), rough=0.34, metal=0.3, coat=0.25),
    lpc=new_mat('LPC_Titanium', (0.66, 0.64, 0.60), rough=0.26, metal=1.0),
    hpc=new_mat('HPC_Steel', (0.80, 0.81, 0.83), rough=0.20, metal=1.0),
    stator=new_mat('Stator_DarkSteel', (0.42, 0.43, 0.45), rough=0.32, metal=1.0),
    comb=new_mat('Combustor_Inconel', (0.62, 0.46, 0.32), rough=0.33, metal=1.0),
    flame=new_mat('Combustor_Glow', (1.0, 0.45, 0.12), rough=0.5, emit=(1.0, 0.38, 0.08), estr=4.0),
    hpt=new_mat('HPT_DarkGold', (0.78, 0.56, 0.26), rough=0.28, metal=1.0),
    lpt=new_mat('LPT_TemperedBlue', (0.36, 0.40, 0.52), rough=0.30, metal=1.0),
    nozzle=new_mat('Exhaust_HeatTint', (0.30, 0.27, 0.25), rough=0.38, metal=1.0),
    lpshaft=new_mat('LP_Shaft_Blue', (0.10, 0.22, 0.55), rough=0.25, metal=1.0),
    hpshaft=new_mat('HP_Shaft_Copper', (0.85, 0.38, 0.15), rough=0.25, metal=1.0),
    casing=new_mat('Casing_Gunmetal', (0.20, 0.21, 0.22), rough=0.40, metal=1.0),
    disc=new_mat('Disc_Steel', (0.55, 0.56, 0.58), rough=0.30, metal=1.0),
    bearing=new_mat('Bearing_Brass', (0.72, 0.58, 0.32), rough=0.30, metal=1.0),
    cap=new_mat('CutFace_Coral', (0.50, 0.095, 0.06), rough=0.55),
    cap_light=new_mat('CutFace_Light', (0.55, 0.42, 0.36), rough=0.6),
    backdrop=new_mat('Backdrop', (0.008, 0.0084, 0.0095), rough=0.85),
    ref=new_mat('RefLine', (1, 0.1, 0.1), emit=(1, 0.15, 0.1), estr=4.0),
)

def spinner_material():
    m = bpy.data.materials.new('Spinner_Spiral'); m.use_nodes = True
    nt = m.node_tree; N = nt.nodes; L = nt.links
    b = N['Principled BSDF']
    b.inputs['Roughness'].default_value = 0.22; b.inputs['Coat Weight'].default_value = 0.7
    tc = N.new('ShaderNodeTexCoord'); sx = N.new('ShaderNodeSeparateXYZ')
    at = N.new('ShaderNodeMath'); at.operation = 'ARCTAN2'
    dv = N.new('ShaderNodeMath'); dv.operation = 'DIVIDE'; dv.inputs[1].default_value = 2 * math.pi
    mx = N.new('ShaderNodeMath'); mx.operation = 'MULTIPLY'; mx.inputs[1].default_value = -2.2
    ad = N.new('ShaderNodeMath'); ad.operation = 'ADD'
    fr = N.new('ShaderNodeMath'); fr.operation = 'FRACT'
    lt = N.new('ShaderNodeMath'); lt.operation = 'LESS_THAN'; lt.inputs[1].default_value = 0.10
    mix = N.new('ShaderNodeMix'); mix.data_type = 'RGBA'
    mix.inputs['A'].default_value = (0.03, 0.032, 0.035, 1); mix.inputs['B'].default_value = (0.85, 0.85, 0.83, 1)
    L.new(tc.outputs['Object'], sx.inputs[0])
    L.new(sx.outputs['Z'], at.inputs[0]); L.new(sx.outputs['Y'], at.inputs[1])
    L.new(at.outputs[0], dv.inputs[0]); L.new(sx.outputs['X'], mx.inputs[0])
    L.new(dv.outputs[0], ad.inputs[0]); L.new(mx.outputs[0], ad.inputs[1])
    L.new(ad.outputs[0], fr.inputs[0]); L.new(fr.outputs[0], lt.inputs[0])
    L.new(lt.outputs[0], mix.inputs['Factor']); L.new(mix.outputs['Result'], b.inputs['Base Color'])
    m.diffuse_color = (0.05, 0.05, 0.05, 1)
    return m
M['spinner'] = spinner_material()
M['lpshaft_cap'] = new_mat('CutFace_LPShaft', (0.12, 0.30, 0.75), rough=0.5)
M['hpshaft_cap'] = new_mat('CutFace_HPShaft', (0.95, 0.50, 0.15), rough=0.5)
M['backdrop'].node_tree.nodes['Principled BSDF'].inputs['Specular IOR Level'].default_value = 0.15

# ------------------------------------------------------------------ collections (10 named parts + structure)
C_FAN = sub('01_Fan'); C_LPC = sub('02_LPC_Booster'); C_HPC = sub('03_HPC'); C_CMB = sub('04_Combustor')
C_HPT = sub('05_HPT'); C_LPT = sub('06_LPT'); C_NOZ = sub('07_Exhaust_Nozzle'); C_BYP = sub('08_Bypass_Duct')
C_NAC = sub('09_Nacelle'); C_SHF = sub('10_Shafts_DualRotor'); C_STR = sub('11_Structure')
C_PYL = sub('12_Pylon_ext')
SHELL = {}   # part -> (coll_360, coll_cut)
for key, parent in (('Nacelle', C_NAC), ('BypassDuct', C_BYP), ('Exhaust', C_NOZ)):
    SHELL[key] = (sub(key + '_360', parent), sub(key + '_cut', parent))

def revolve_shell(key, name, prof, mat, cap):
    """Outer shells exist twice: full 360 (Exterior scene) and cut (Cutaway scene)."""
    c360, ccut = SHELL[key]
    if not SIDE:
        revolve(name + '_360', prof, mat, cap, c360, full=True)
    revolve(name + '_cut', prof, mat, cap, ccut, full=False)

# ------------------------------------------------------------------ flow path (station table)
# core annulus hub / tip radii vs axial x
HUB = [(0.56, 0.35), (0.66, 0.368), (0.98, 0.392), (1.05, 0.36), (1.12, 0.262), (1.18, 0.212), (1.96, 0.218),
       (2.00, 0.19), (2.24, 0.19), (2.28, 0.236), (2.48, 0.242), (2.58, 0.262), (3.24, 0.29), (3.34, 0.29)]
TIP = [(0.56, 0.495), (0.66, 0.488), (0.98, 0.455), (1.05, 0.43), (1.12, 0.342), (1.18, 0.300), (1.96, 0.240),
       (2.00, 0.372), (2.22, 0.372), (2.28, 0.308), (2.48, 0.322), (2.58, 0.36), (3.24, 0.455), (3.34, 0.455)]
# bypass duct outer wall (fan case + thrust-reverser inner wall), inner flow surface
DUCT = [(0.0, R_FAN + 0.005), (0.65, R_FAN + 0.005), (1.0, 0.99), (1.5, 0.965), (1.85, 0.93), (2.10, 0.885)]
# core cowl outer surface (= bypass duct inner wall)
COWL = [(0.552, 0.497), (0.60, 0.532), (0.75, 0.58), (1.0, 0.62), (1.3, 0.645), (1.8, 0.64), (2.2, 0.615),
        (2.6, 0.585), (3.0, 0.535), (3.25, 0.50)]
X_FAN = 0.40

# ------------------------------------------------------------------ 09 nacelle + 08 bypass duct
nac_outer = [(-0.80, 1.00), (-0.785, 1.04), (-0.74, 1.075), (-0.60, 1.11), (-0.30, 1.14), (0.20, 1.158),
             (0.80, 1.152), (1.30, 1.118), (1.70, 1.06), (2.10, 0.946)]
inlet = [(0.0, R_FAN + 0.005), (-0.15, 0.975), (-0.40, 0.948), (-0.62, 0.932), (-0.72, 0.938), (-0.77, 0.953),
         (-0.795, 0.975)]
duct_top = [(x, r + 0.03) for (x, r) in DUCT]
nac_prof = nac_outer + [duct_top[-1]] + list(reversed(duct_top[:-1])) + inlet
revolve_shell('Nacelle', 'Nacelle', nac_prof, M['nacelle'], M['cap_light'])
if not SIDE:
    seam = new_mat('Nacelle_Seam', (0.04, 0.04, 0.045), rough=0.6)
    for i, xs in enumerate((0.0, 1.32)):
        ro = interp(nac_outer, xs)
        revolve(f'Nacelle_SeamLine_{i+1}', [(xs - 0.004, ro - 0.01), (xs + 0.004, ro - 0.01), (xs + 0.004, ro + 0.0015),
                (xs - 0.004, ro + 0.0015)], seam, seam, SHELL['Nacelle'][0], full=True)
revolve_shell('BypassDuct', 'BypassDuct_OuterWall', shell(DUCT, 0.03), M['duct'], M['cap_light'])
cowl_prof = COWL + [(x, r - 0.02) for (x, r) in reversed(COWL[1:])] + [(0.565, 0.492)]
revolve_shell('BypassDuct', 'CoreCowl', cowl_prof, M['duct'], M['cap_light'])
# outlet guide vanes in the bypass stream (count stylized)
blade_row('Bypass_OGV', C_BYP, M['stator'], 0.95, 40, interp(COWL, 0.95) + 0.004, interp(DUCT, 0.95) - 0.004,
          const(0.15), const(math.radians(12)), const(0.07), const(0.025), sign=-1, nsec=4, npts=14)

# ------------------------------------------------------------------ 01 fan: spinner, 18 blades, disc
spin_prof = [(-0.13, 0.003), (-0.10, 0.06), (-0.04, 0.13), (0.05, 0.20), (0.15, 0.25), (0.26, 0.288),
             (0.34, 0.300), (0.56, 0.318), (0.56, 0.20), (0.40, 0.06), (0.30, 0.003)]
revolve('Spinner_FanHub', spin_prof, M['spinner'], M['cap'], C_FAN, full=True)
fan_hub = lambda x: interp([(0.26, 0.288), (0.34, 0.300), (0.56, 0.318)], x)
blade_row('Fan_Blades_x18', C_FAN, M['fan'], X_FAN, LEAP['fan_blades'], fan_hub(X_FAN) - 0.01, R_FAN - 0.008,
          chord=lambda f: 0.27 + 0.17 * f ** 0.8, stagger=lambda f: math.radians(24 + 38 * f ** 0.9),
          tc=lambda f: 0.10 - 0.075 * f, camber=lambda f: 0.075 - 0.05 * f, sign=1, nsec=12, npts=28,
          sweep=lambda f: 0.07 * f * f - 0.02 * f, cut=not FAN_FULL)
revolve('Fan_Disc', [(0.33, 0.07), (0.47, 0.07), (0.47, 0.12), (0.43, 0.16), (0.43, 0.26), (0.50, 0.27),
                     (0.50, 0.30), (0.30, 0.30), (0.30, 0.27), (0.37, 0.26), (0.37, 0.16), (0.33, 0.12)],
        M['disc'], M['cap'], C_FAN)

# ------------------------------------------------------------------ rotor disc profile
def disc_prof(xc, r_bore, r_rim, w_rim, w_web=0.010, w_bore=0.035, h_rim=0.018, h_bore=0.025):
    hb = r_bore + h_bore; rr = r_rim - h_rim
    return [(xc - w_bore / 2, r_bore), (xc + w_bore / 2, r_bore), (xc + w_bore / 2, hb), (xc + w_web / 2, hb + 0.012),
            (xc + w_web / 2, rr), (xc + w_rim / 2, rr), (xc + w_rim / 2, r_rim), (xc - w_rim / 2, r_rim),
            (xc - w_rim / 2, rr), (xc - w_web / 2, rr), (xc - w_web / 2, hb + 0.012), (xc - w_bore / 2, hb)]

def rows_between(x0, x1, kinds):
    n = len(kinds); dx = (x1 - x0) / (n - 1)
    return [(x0 + i * dx, k) for i, k in enumerate(kinds)], dx

def turbomachine(prefix, c, x0, x1, kinds, rot_mat, stat_mat, n_rot, n_stat, comp=True, bore=0.11,
                 disc_mat=None, drum=True, nsec=4):
    rows, dx = rows_between(x0, x1, kinds)
    ax = dx * 0.72
    ri = si = 0
    for x, k in rows:
        h, t = interp(HUB, x), interp(TIP, x)
        if k == 'R':
            ri += 1
            n = n_rot(ri)
            if comp:
                st, cam = lin(math.radians(38), math.radians(55)), const(0.03)
            else:
                st, cam = lin(math.radians(30), math.radians(40)), const(0.10)
            blade_row(f'{prefix}_R{ri}_x{n}', c, rot_mat, x, n, h + 0.002, t - 0.004, const(ax / 0.75),
                      st, const(0.09 if comp else 0.20), cam, sign=1 if comp else -1, nsec=nsec)
            revolve(f'{prefix}_Disc{ri}', disc_prof(x, bore, h + 0.001, ax * 1.05), disc_mat or M['disc'],
                    M['cap'], c, seg_scale=0.7)
        else:
            si += 1
            n = n_stat(si)
            lab = {'G': 'IGV', 'S': f'S{si}', 'N': f'N{si}'}[k]
            if comp:
                st, cam = lin(math.radians(28), math.radians(34)), const(0.03)
            else:
                st, cam = lin(math.radians(45), math.radians(50)), const(0.11)
            blade_row(f'{prefix}_{lab}_x{n}', c, stat_mat, x, n, h + 0.001, t - 0.001, const(ax / 0.75),
                      st, const(0.09 if comp else 0.22), cam, sign=-1 if comp else 1, nsec=nsec, phase=0.5)
    if drum:
        pts = [(x, interp(HUB, x)) for x in [x0 - dx * 0.6 + i * (x1 - x0 + dx * 1.2) / 12 for i in range(13)]]
        revolve(f'{prefix}_Drum', shell_in(pts, 0.012), disc_mat or M['disc'], M['cap'], c)
    return rows

# ------------------------------------------------------------------ 02 LPC booster: 3 rotors + 4 stator rows
turbomachine('LPC', C_LPC, 0.64, 0.97, ['S', 'R', 'S', 'R', 'S', 'R', 'S'], M['lpc'], M['stator'],
             n_rot=lambda i: 64, n_stat=lambda i: 80, bore=0.30, nsec=4)
# booster spool cone from fan disc
revolve('LPC_SpoolCone', [(0.49, 0.27), (0.62, 0.345), (0.62, 0.357), (0.49, 0.284)], M['disc'], M['cap'], C_LPC)

# ------------------------------------------------------------------ 03 HPC: IGV + 10 rotors + 9 stators
hpc_kinds = ['G'] + sum([['R', 'S'] for _ in range(9)], []) + ['R']
turbomachine('HPC', C_HPC, 1.19, 1.94, hpc_kinds, M['hpc'], M['stator'],
             n_rot=lambda i: 34 + 3 * i, n_stat=lambda i: 44 + 3 * i, bore=0.105, nsec=4)

# ------------------------------------------------------------------ 04 combustor: annular liner + 19 nozzles
liner = [(2.005, 0.300), (2.02, 0.338), (2.20, 0.338), (2.255, 0.313), (2.255, 0.306), (2.20, 0.331),
         (2.025, 0.331), (2.012, 0.300), (2.012, 0.250), (2.025, 0.222), (2.20, 0.227), (2.255, 0.244),
         (2.255, 0.237), (2.20, 0.220), (2.02, 0.215), (2.005, 0.250)]
revolve('Combustor_Liner', liner, M['comb'], M['cap'], C_CMB)
flame = [(2.11 + 0.075 * math.cos(2 * math.pi * k / 20), 0.276 + 0.034 * math.sin(2 * math.pi * k / 20)) for k in range(20)]
revolve('Combustor_FlameZone', flame, M['flame'], M['flame'], C_CMB)
revolve('Combustor_OuterCase', shell([(1.97, 0.372), (2.24, 0.372)], 0.012), M['casing'], M['cap'], C_CMB)
revolve('Combustor_InnerCase', shell_in([(1.97, 0.19), (2.25, 0.19)], 0.010), M['casing'], M['cap'], C_CMB)
revolve('HPC_Diffuser', shell([(1.94, 0.236), (1.975, 0.25), (2.0, 0.27)], 0.01), M['comb'], M['cap'], C_CMB)
bm = bmesh.new()
for k in range(LEAP['fuel_nozzles']):
    th = 2 * math.pi * (k + 0.25) / LEAP['fuel_nozzles']
    if in_cut(th, margin=math.radians(3)): continue
    cy, sz = math.cos(th), math.sin(th)
    cylinder_between(bm, (1.985, 0.378 * cy, 0.378 * sz), (1.99, 0.29 * cy, 0.29 * sz), 0.0065)
    cylinder_between(bm, (1.988, 0.276 * cy, 0.276 * sz), (2.012, 0.276 * cy, 0.276 * sz), 0.016, nv=14)
mesh_obj('Combustor_FuelNozzles_x19', bm, [M['comb']], C_CMB, sharp_deg=50)

# ------------------------------------------------------------------ 05 HPT: 2 stages
turbomachine('HPT', C_HPT, 2.285, 2.46, ['N', 'R', 'N', 'R'], M['hpt'], M['hpt'],
             n_rot=lambda i: 52, n_stat=lambda i: 34 + 8 * (i - 1), comp=False, bore=0.105, nsec=4)

# ------------------------------------------------------------------ 06 LPT: 7 stages
lpt_kinds = sum([['N', 'R'] for _ in range(7)], [])
turbomachine('LPT', C_LPT, 2.60, 3.20, lpt_kinds, M['lpt'], M['lpt'],
             n_rot=lambda i: 70 + 4 * i, n_stat=lambda i: 64 + 4 * i, comp=False, bore=0.07, nsec=4)

# ------------------------------------------------------------------ 11 structure: core casing, frames, struts, bearings
core_case = [(x, interp(TIP, x)) for x in [0.60 + i * (3.34 - 0.60) / 110 for i in range(111)]]
core_case = [p for p in core_case if not (1.965 < p[0] < 2.245)]   # combustor case is its own part
seg1 = [p for p in core_case if p[0] <= 1.965]; seg2 = [p for p in core_case if p[0] >= 2.245]
revolve('Core_Casing_Fwd', shell(seg1, 0.012), M['casing'], M['cap'], C_STR)
revolve('Core_Casing_Aft', shell(seg2, 0.012), M['casing'], M['cap'], C_STR)
goose = [(x, interp(HUB, x)) for x in [0.975 + i * 0.21 / 10 for i in range(11)]]
revolve('FanHubFrame_InnerWall', shell_in(goose, 0.012), M['casing'], M['cap'], C_STR)
blade_row('FanHubFrame_Struts', C_STR, M['casing'], 1.06, 10, interp(HUB, 1.06), interp(TIP, 1.06),
          const(0.075), const(0.0), const(0.22), const(0.0), nsec=3, npts=12)
blade_row('TurbineCenterFrame_Vanes', C_STR, M['casing'], 2.53, 14, interp(HUB, 2.53), interp(TIP, 2.53),
          const(0.07), const(math.radians(10)), const(0.25), const(0.02), nsec=3, npts=12)
blade_row('TurbineRearFrame_Struts', C_STR, M['casing'], 3.285, 10, 0.29, 0.455, const(0.075),
          const(math.radians(8)), const(0.20), const(0.0), nsec=3, npts=12)
for i, xb in enumerate((0.52, 1.13, 2.50, 3.27)):          # bearing housings (P2)
    revolve(f'Bearing_{i+1}', [(xb - 0.025, 0.065), (xb + 0.025, 0.065), (xb + 0.025, 0.105), (xb - 0.025, 0.105)],
            M['bearing'], M['cap'], C_STR, seg_scale=0.6)

# ------------------------------------------------------------------ 10 dual-rotor shafts
revolve('LP_Shaft', shell([(0.40, 0.040), (0.55, 0.040), (3.20, 0.040), (3.40, 0.040)], 0.022),
        M['lpshaft'], M['lpshaft_cap'], C_SHF, seg_scale=0.7)
revolve('LP_Shaft_TurbineCone', [(3.10, 0.062), (3.13, 0.062), (3.13, 0.09), (3.00, 0.265), (2.975, 0.265), (2.975, 0.245)], M['lpshaft'], M['lpshaft_cap'], C_SHF)
revolve('HP_Shaft', shell([(1.10, 0.082), (2.52, 0.082)], 0.016), M['hpshaft'], M['hpshaft_cap'], C_SHF, seg_scale=0.7)
revolve('HP_Shaft_FwdCone', [(1.10, 0.096), (1.18, 0.20), (1.19, 0.20), (1.115, 0.096)], M['hpshaft'], M['hpshaft_cap'], C_SHF)
revolve('HP_Shaft_AftCone', [(2.26, 0.22), (2.40, 0.098), (2.415, 0.098), (2.275, 0.22)], M['hpshaft'], M['hpshaft_cap'], C_SHF)

# ------------------------------------------------------------------ 07 exhaust: core nozzle + plug
revolve_shell('Exhaust', 'CoreNozzle', [(3.25, 0.455), (3.56, 0.428), (3.56, 0.436), (3.25, 0.50)], M['nozzle'], M['cap'])
plug_o = [(3.24, 0.29), (3.40, 0.285), (3.60, 0.252), (3.78, 0.18), (3.92, 0.085), (3.99, 0.02), (4.0, 0.003)]
plug_prof = plug_o + [(3.92, 0.003), (3.78, 0.165), (3.60, 0.238), (3.40, 0.271), (3.25, 0.276)]
revolve_shell('Exhaust', 'ExhaustPlug', plug_prof, M['nozzle'], M['cap'])

# ------------------------------------------------------------------ 12 pylon stub (exterior only, P2)
if not SIDE:
    bm = bmesh.new()
    outline = [(0.30, 1.12), (1.40, 1.09), (2.10, 0.93), (2.70, 0.62), (3.15, 0.58), (3.15, 0.70), (2.45, 1.25), (2.10, 1.55),
               (0.10, 1.55)]
    w = 0.15
    top = [bm.verts.new((x, -w * (0.6 if x > 2.6 else 1.0), z)) for x, z in outline]
    bot = [bm.verts.new((x, w * (0.6 if x > 2.6 else 1.0), z)) for x, z in outline]
    bm.faces.new(top); bm.faces.new(list(reversed(bot)))
    n = len(outline)
    for j in range(n):
        bm.faces.new((top[j], top[(j + 1) % n], bot[(j + 1) % n], bot[j]))
    o = mesh_obj('Pylon_Stub', bm, [M['nacelle']], C_PYL, sharp_deg=30)
    bv = o.modifiers.new('bevel', 'BEVEL'); bv.width = 0.06; bv.segments = 4; bv.limit_method = 'ANGLE'

# ------------------------------------------------------------------ studio: cyclorama bowl, lights, cameras
C_STU = bpy.data.collections.new('Studio_Common')
C_SCUT = bpy.data.collections.new('Studio_Cutaway')
C_SEXT = bpy.data.collections.new('Studio_Exterior')
bowl = [(0.0, -1.45), (9.0, -1.45), (11.0, -1.0), (12.2, 0.5), (12.6, 3.0), (12.7, 9.0), (12.75, 9.0)]
bm = bmesh.new()
nb = 96
rings = [[bm.verts.new((1.6 + r * math.cos(2 * math.pi * i / nb), r * math.sin(2 * math.pi * i / nb), z)) for r, z in bowl]
         for i in range(nb)]
for i in range(nb):
    A, B = rings[i], rings[(i + 1) % nb]
    for j in range(len(bowl) - 1):
        bm.faces.new((A[j], A[j + 1], B[j + 1], B[j]))
bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-4)
mesh_obj('Cyclorama', bm, [M['backdrop']], C_STU, sharp_deg=80)

def area(name, c, loc, target, power, size, color=(1, 1, 1), shape='RECTANGLE', size_y=None, spread=180):
    ld = bpy.data.lights.new(name, 'AREA'); ld.energy = power; ld.color = color; ld.shape = shape
    ld.spread = math.radians(spread)
    ld.size = size
    if size_y: ld.size_y = size_y
    o = bpy.data.objects.new(name, ld); o.location = loc
    o.visible_camera = False
    d = Vector(target) - Vector(loc)
    o.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    c.objects.link(o)
    return o

def camera(name, c, loc, target, lens, ortho=None):
    cd = bpy.data.cameras.new(name); cd.lens = lens; cd.sensor_width = 36
    cd.clip_start = 0.05; cd.clip_end = 100
    if ortho: cd.type = 'ORTHO'; cd.ortho_scale = ortho
    o = bpy.data.objects.new(name, cd); o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    c.objects.link(o)
    return o

CENTER = Vector((1.55, 0, 0))
# Cutaway lighting: key from upper front-left, rim from behind, warm-neutral fill into the open wedge
area('Cut_Key', C_SCUT, (-1.5, -4.5, 5.0), CENTER, 2000, 3.5, (1.0, 0.97, 0.93), size_y=2.5)
area('Cut_Fill', C_SCUT, (-3.5, 2.0, 1.0), CENTER, 500, 4.0, (0.85, 0.9, 1.0))
area('Cut_Rim', C_SCUT, (4.5, 3.5, 3.5), CENTER, 1600, 3.0, (0.9, 0.95, 1.0))
area('Cut_InteriorFill', C_SCUT, (1.7, -1.5, 2.3), (1.8, 0.0, 0.0), 750, 2.6, (1.0, 0.96, 0.9), size_y=0.8)
area('Cut_Floor_Kick', C_SCUT, (1.6, -3.0, -1.2), CENTER, 120, 4.0, (0.8, 0.85, 1.0), size_y=1.0)
# Exterior lighting
area('Ext_Key', C_SEXT, (-3.5, -5.0, 3.5), CENTER, 1700, 4.0, (1.0, 0.97, 0.93), size_y=2.5)
area('Ext_Fill', C_SEXT, (-4.0, 3.5, 0.0), CENTER, 600, 4.0, (0.85, 0.9, 1.0))
area('Ext_Rim', C_SEXT, (5.0, 2.5, 3.5), CENTER, 2000, 3.0, (0.9, 0.95, 1.0))
area('Ext_Top', C_SEXT, (1.5, 0.0, 5.0), CENTER, 900, 6.0, (1, 1, 1), size_y=2.0)
area('Ext_AftKick', C_SEXT, (4.8, -3.6, 0.6), (3.3, 0, 0), 500, 2.0, (0.9, 0.95, 1.0))
area('Ext_Inlet', C_SEXT, (-3.2, -1.6, 0.2), (0.4, 0, 0), 400, 1.5, (1.0, 0.97, 0.93))

CAM_CUT = camera('Cam_Cutaway', C_SCUT, (float(kv.get('cx', 0.2)), float(kv.get('cy', -6.4)), float(kv.get('cz', 4.7))), (1.5, 0.05, -0.12), float(kv.get('lens', 50)))
CAM_EXT = camera('Cam_Exterior', C_SEXT, (-5.3, -5.9, -0.05), (1.25, 0.0, -0.05), 48)
if VIEW == 'fanfront':
    CAM_CUT = camera('Cam_FanFront', C_SCUT, (-4.5, -0.6, 0.4), (0.4, 0, 0), 60)
if VIEW == 'fanside':
    CAM_CUT = camera('Cam_FanSide', C_SCUT, (0.3, -4.2, 2.6), (0.4, 0, 0.3), 60)
if SIDE:
    CAM_CUT = camera('Cam_Side', C_SCUT, (1.6, -10, 0), (1.6, 0, 0), 50, ortho=5.6)
    # proportion reference bars (geometry, preview only): x=0, x=3.328, r=+-fan radius
    bm = bmesh.new()
    def bar(p0, p1, w=0.008):
        cylinder_between(bm, p0, p1, w, nv=6)
    bar((0, -1.4, -1.3), (0, -1.4, 1.3)); bar((LEAP['length'], -1.4, -1.3), (LEAP['length'], -1.4, 1.3))
    bar((-0.95, -1.4, R_FAN), (4.1, -1.4, R_FAN)); bar((-0.95, -1.4, -R_FAN), (4.1, -1.4, -R_FAN))
    mesh_obj('RefBars', bm, [M['ref']], C_SCUT)

# world: dark procedural gradient (no HDRI)
W = bpy.data.worlds.new('StudioWorld'); W.use_nodes = True
bg = W.node_tree.nodes['Background']; bg.inputs['Color'].default_value = (0.012, 0.013, 0.016, 1); bg.inputs['Strength'].default_value = 1.0

# ------------------------------------------------------------------ scene assembly
def find_lc(lc, name):
    if lc.collection.name == name: return lc
    for ch in lc.children:
        r = find_lc(ch, name)
        if r: return r

for sc, studio, excl in ((SC_CUT, C_SCUT, '_360'), (SC_EXT, C_SEXT, '_cut')):
    for c in (ROOT, C_STU, studio):
        sc.collection.children.link(c)
    sc.world = W
    vl = sc.view_layers[0]
    for name in list(COLLS):
        if name.endswith(excl) or (name == '12_Pylon_ext' and (sc is SC_CUT or not PYLON)):
            lc = find_lc(vl.layer_collection, name)
            if lc: lc.exclude = True
SC_CUT.camera = CAM_CUT; SC_EXT.camera = CAM_EXT

def render_setup(sc):
    sc.render.engine = 'CYCLES'
    cy = sc.cycles
    cy.device = 'CPU'
    cy.use_denoising = True; cy.denoiser = 'OPENIMAGEDENOISE'
    cy.use_adaptive_sampling = True; cy.adaptive_threshold = 0.02
    cy.max_bounces = 8; cy.diffuse_bounces = 3; cy.glossy_bounces = 4; cy.transmission_bounces = 2
    cy.volume_bounces = 0; cy.transparent_max_bounces = 4
    cy.sample_clamp_indirect = 6.0
    cy.caustics_reflective = False; cy.caustics_refractive = False
    cy.blur_glossy = 0.5
    cy.use_auto_tile = True; cy.tile_size = 1024
    r = sc.render
    r.threads_mode = 'FIXED'; r.threads = 6
    r.use_stamp = False
    for a in dir(r):
        if a.startswith('use_stamp_'):
            try: setattr(r, a, False)
            except Exception: pass
    r.film_transparent = False
    r.image_settings.file_format = 'PNG'; r.image_settings.color_depth = '8'; r.image_settings.color_mode = 'RGB'
    sc.view_settings.view_transform = 'AgX'
    try: sc.view_settings.look = 'AgX - Medium High Contrast'
    except Exception as e: print('look not set', e)
    sc.frame_start = sc.frame_end = 1
    # compositor: gentle vignette only (product shot), no bloom streaks
    sc.use_nodes = True
    nt = sc.node_tree
    for nd in list(nt.nodes): nt.nodes.remove(nd)
    rl = nt.nodes.new('CompositorNodeRLayers')
    el = nt.nodes.new('CompositorNodeEllipseMask'); el.width = 1.05; el.height = 0.95
    bl = nt.nodes.new('CompositorNodeBlur'); bl.size_x = 300; bl.size_y = 220; bl.use_relative = False
    mp = nt.nodes.new('CompositorNodeMapRange')
    mp.inputs['From Min'].default_value = 0.0; mp.inputs['From Max'].default_value = 1.0
    mp.inputs['To Min'].default_value = 0.55; mp.inputs['To Max'].default_value = 1.0
    mx = nt.nodes.new('CompositorNodeMixRGB'); mx.blend_type = 'MULTIPLY'; mx.inputs[0].default_value = 1.0
    comp = nt.nodes.new('CompositorNodeComposite')
    nt.links.new(el.outputs['Mask'], bl.inputs['Image']); nt.links.new(bl.outputs['Image'], mp.inputs['Value'])
    nt.links.new(rl.outputs['Image'], mx.inputs[1]); nt.links.new(mp.outputs['Value'], mx.inputs[2])
    nt.links.new(mx.outputs['Image'], comp.inputs['Image'])

for sc in (SC_CUT, SC_EXT):
    render_setup(sc)
SC_EXT.view_settings.exposure = -0.35

# sanity: no text objects anywhere
assert not [o for o in bpy.data.objects if o.type == 'FONT'], 'text object found'
tot = sum(STATS.values())
print(f'[engine] objects={len(STATS)} verts={tot} build={time.time() - T0:.1f}s mode={MODE} view={VIEW} '
      f'span={math.degrees(CUT_SPAN):.0f}')
for k in sorted(STATS, key=STATS.get, reverse=True)[:8]:
    print(f'   {k}: {STATS[k]}')

# ------------------------------------------------------------------ modes
def do_render(sc, w, h, samples, path, thr=None):
    sc.render.resolution_x, sc.render.resolution_y = w, h; sc.render.resolution_percentage = 100
    sc.cycles.samples = samples
    if thr: sc.cycles.adaptive_threshold = thr
    sc.render.filepath = path
    t = time.time()
    assert bpy.context.scene == sc, 'render scene must be the context scene'
    bpy.ops.render.render(write_still=True)
    print(f'[engine] rendered {path} {w}x{h} samples={samples} in {time.time() - t:.1f}s')

sc = SC_EXT if (VIEW == 'ext' and not SIDE) else SC_CUT
os.makedirs(f'{OUT}/previews', exist_ok=True); os.makedirs(f'{OUT}/renders', exist_ok=True)
if MODE == 'side':
    sc.cycles.use_denoising = True
    do_render(sc, int(kv.get('w', 1280)), int(kv.get('h', 640)), int(kv.get('samples', 24)),
              f'{OUT}/previews/side{TAG}.png')
elif MODE == 'preview':
    do_render(sc, 640, 360, int(kv.get('samples', 16)), f'{OUT}/previews/prev{TAG}_{VIEW}.png')
elif MODE == 'mid':
    do_render(sc, 1280, 720, int(kv.get('samples', 64)), f'{OUT}/previews/mid{TAG}_{VIEW}.png')
elif MODE == 'still':
    name = 'cutaway' if VIEW == 'cut' else 'exterior'
    do_render(sc, 1920, 1080, int(kv.get('samples', 256)), kv.get('out', f'{OUT}/renders/{name}.png'),
              thr=float(kv.get('thr', 0.015)))
elif MODE == 'setup':
    bpy.context.window_manager  # noqa
    bpy.ops.wm.save_as_mainfile(filepath=f'{OUT}/engine.blend', compress=True)
    print('[engine] saved engine.blend')
