"""finalize.py: a test print of a section of a part (the part cut by a box). finalize compares the
printed piece with the part as it is now, cut by that box, and lets the print stand for a promise
only where the promise's joints and measurements check the part inside the box."""
from __future__ import annotations

import math
import os
import re

import validate
from finalize_common import FinalizeError, finite, load_json, rel

SECTION_KEYS = ("box", "stl")

# The printed piece is the part cut by its box when their symmetric difference (the piece less the
# part cut here, plus the part cut here less the piece) is at most max(DIFF_FLOOR_MM3, DIFF_REL *
# the piece's volume). A piece built by the part's own generator with the cut added differs from
# the part cut here by float rounding alone: about 1e-4 mm3 on a 49 cm3 piece with 39 000 mm2 of
# surface, while a box 0.01 mm off differs by 9 mm3.
DIFF_FLOOR_MM3 = 0.1
DIFF_REL = 1e-6

# A joint checks a part inside the box when the part outside the box keeps at least MARGIN_MM,
# plus the fit's largest play, from the mating part as the fit report placed them (through the
# whole sweep for a moving joint); a measurement, when the part outside the box keeps MARGIN_MM
# from the plane it sliced or the rays it cast. The margin is room for a print that does not come
# out at the model's size, and keeps the place checked away from the cut.
MARGIN_MM = 1.0

SWEEP_TURNS = 2000          # turns followed at most to keep a moving joint inside the box


def m3d_or_none():
    try:
        import manifold3d as m3d
        import numpy  # noqa: F401
    except ImportError:
        return None
    return m3d


def box_of(sec):
    """The section's box as ((x0, y0, z0), (x1, y1, z1)), or None when it is not one."""
    box = sec.get("box") if isinstance(sec, dict) else None
    if not (isinstance(box, list) and len(box) == 2
            and all(isinstance(c, list) and len(c) == 3 and all(finite(x) for x in c) for c in box)):
        return None
    lo, hi = box
    if not all(lo[i] < hi[i] for i in range(3)):
        return None
    return tuple(float(x) for x in lo), tuple(float(x) for x in hi)


def section_problem(sec, part):
    """Why the section declared for a printed part is not {"box": [[x0, y0, z0], [x1, y1, z1]],
    "stl": "<the printed piece's STL, relative to the project folder>"}, or None."""
    if not isinstance(sec, dict):
        return (f"the section of {part} must be {{\"box\": [[x0, y0, z0], [x1, y1, z1]], \"stl\": \"<the printed "
                "piece's STL>\"}")
    unknown = sorted(k for k in sec if k not in SECTION_KEYS)
    if unknown:
        return f"the section of {part} has an unknown field {', '.join(unknown)} (fields: {', '.join(SECTION_KEYS)})"
    if box_of(sec) is None:
        return (f"the section box of {part} must be [[x0, y0, z0], [x1, y1, z1]], in mm in the coordinates of "
                f"{part}'s STL, each low corner below its high one")
    stl = sec.get("stl")
    if not (isinstance(stl, str) and stl.strip()):
        return f"the section of {part} needs stl, the path of the printed piece's STL"
    if os.path.isabs(stl) or re.match(r"^([A-Za-z]:|[\\/~])", stl) or ".." in re.split(r"[\\/]", stl):
        return f"the section of {part}: stl must be a path in the project folder, relative to it (not {stl})"
    return None


def _solid_box(m3d, lo, hi):
    return m3d.Manifold.cube([hi[i] - lo[i] for i in range(3)]).translate(list(lo))


def _volume(m):
    return 0.0 if m.is_empty() else m.volume()


def compare_section(part_stl, sec, sha):
    """Whether the printed piece (sec["stl"], printed as `sha`) is the part as it is now (its STL
    `part_stl`) cut by the box. Returns {box, piece, state, note?, volume_mm3?, difference_mm3?,
    tolerance_mm3?}: state `same`, `differs` (more than the tolerance), `missing` (the piece's STL
    is gone or is not the one printed) or `unchecked` (no manifold3d, or a mesh that is not
    closed)."""
    lo, hi = box_of(sec)
    piece = sec["stl"]
    out = {"box": [list(lo), list(hi)], "piece": rel(piece)}
    if not os.path.isfile(piece):
        out.update(state="missing", note=f"{rel(piece)} not found")
        return out
    if validate.file_sha256(piece) != sha:
        out.update(state="missing", note=f"{rel(piece)} is not the piece that was printed (its sha256 is not the one "
                                         "recorded)")
        return out
    m3d = m3d_or_none()
    if m3d is None:
        out.update(state="unchecked", note="no manifold3d to compare the piece (pip install manifold3d)")
        return out
    import fit
    try:
        whole, got = fit.load_part(part_stl, m3d), fit.load_part(piece, m3d)
    except fit.FitError as exc:
        out.update(state="unchecked", note=str(exc))
        return out
    cut = whole ^ _solid_box(m3d, lo, hi)
    diff = _volume(got - cut) + _volume(cut - got)
    tol = max(DIFF_FLOOR_MM3, DIFF_REL * _volume(got))
    out.update(state="same" if diff <= tol else "differs", volume_mm3=round(_volume(got), 3),
               difference_mm3=round(diff, 4), tolerance_mm3=round(tol, 4))
    return out


def _vec3(v):
    return isinstance(v, list) and len(v) == 3 and all(finite(x) for x in v)


def _placement(placed, side):
    """(rotate_deg, translate_mm) of one side of a fit report, or None."""
    p = placed.get(side) if isinstance(placed, dict) else None
    if not (isinstance(p, dict) and _vec3(p.get("rotate_deg")) and _vec3(p.get("translate_mm"))):
        return None
    return [float(x) for x in p["rotate_deg"]], [float(x) for x in p["translate_mm"]]


def _same_path(a, b):
    return bool(isinstance(a, str) and isinstance(b, str)
                and os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b)))


class Regions:
    """Where a promise's joints and measurements check a part, against the box of a section of
    that part. Each mesh, and each part less a box, is computed once per run."""

    def __init__(self, parts):
        self.parts = {p.get("name"): p for p in parts if isinstance(p.get("name"), str)}
        self.meshes, self.cut = {}, {}

    def mesh(self, path):
        import fit
        key = os.path.normcase(os.path.abspath(path))
        if key not in self.meshes:
            self.meshes[key] = fit.load_part(path, m3d_or_none())
        return self.meshes[key]

    def outside(self, part, box):
        """The part as it is now, less the box (in the part's own coordinates)."""
        if (part, box) not in self.cut:
            self.cut[(part, box)] = self.mesh(self.parts[part]["stl"]) - _solid_box(m3d_or_none(), *box)
        return self.cut[(part, box)]

    def problem(self, kind, name, raw, entry, part, box):
        """None when the place the joint or measurement `name` checks `part` lies inside the box,
        else why it is not shown to."""
        import fit
        import measure
        what = f"{kind} '{name}'"
        if entry.get("result") in ("missing", "stale"):
            return (f"{what} has no {'fit report' if kind == 'joint' else 'report'} of {part} as it is now to show "
                    "where it checks it")
        try:
            if self.outside(part, box).is_empty():
                return None
            rep = load_json(raw.get("report"), f"{kind} report")
            if not isinstance(rep, dict):
                return f"{what}: its report is not an object"
            return self._joint(what, rep, part, box) if kind == "joint" else self._measurement(what, rep, part, box)
        except (fit.FitError, measure.MeasureError, FinalizeError, OSError, ValueError) as exc:
            return f"where {what} checks {part} cannot be read ({exc})"

    def _joint(self, what, rep, part, box):
        import fit
        rparts = rep.get("parts") if isinstance(rep.get("parts"), dict) else {}
        me = self.parts[part]
        sides = [k for k in ("a", "b")
                 if isinstance(rparts.get(k), dict) and rparts[k].get("sha256") == me.get("sha256")]
        sides = [k for k in sides if _same_path(rparts[k].get("path"), me.get("stl"))] or sides
        metrics = rep.get("metrics") if isinstance(rep.get("metrics"), dict) else {}
        plays = [p["play_mm"] for p in metrics.get("play") or []
                 if isinstance(p, dict) and p.get("contact") is True and finite(p.get("play_mm"))]
        margin = MARGIN_MM + max(plays + [0.0])
        sweep = metrics.get("sweep")
        for k in sides:
            other = "b" if k == "a" else "a"
            mine, theirs = _placement(rep.get("placement"), k), _placement(rep.get("placement"), other)
            path = (rparts.get(other) or {}).get("path")
            if mine is None or theirs is None or not isinstance(path, str):
                return (f"{what}: its report does not record where it placed the parts, so where it checks {part} "
                        "is not known")
            near = fit.place(self.outside(part, box), *mine)
            mate = fit.place(self.mesh(path), *theirs)
            if sweep is None:
                gap = near.min_gap(mate, margin + 1.0)
            else:
                gap, why = _swept_gap(sweep, near, mate, k == "b", margin)
                if why:
                    return f"{what}: {why}"
            if gap < margin - 1e-9:
                return (f"{what} checks {part} outside the section box: {part} comes within {max(gap, 0.0):.2f} mm of "
                        f"{rel(path)} outside it, and the section box must hold all of {part} within "
                        f"{round(margin, 2):g} mm of it")
        return None

    def _measurement(self, what, rep, part, box):
        import measure
        q = rep.get("query") if isinstance(rep.get("query"), dict) else {}
        cmd = q.get("cmd")
        if cmd == "info":
            return f"{what} reads all of {part}, and the section box leaves some of {part} out"
        if cmd not in ("slice", "raymap"):
            return f"{what}: its report records no command that says where it reads {part}"
        whole = self.mesh(self.parts[part]["stl"])
        b = whole.bounding_box()
        lo, hi = list(b[:3]), list(b[3:])
        shift = [-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, 0.0] if q.get("center") else [0.0, 0.0, 0.0]
        axis = str(q.get("axis") or "z").lower()
        if axis not in ("x", "y", "z"):
            return f"{what}: its report names no axis x, y or z"
        a = "xyz".index(axis)
        pad, thin = MARGIN_MM + 1.0, 1e-3
        outside, m3d = self.outside(part, box), m3d_or_none()
        if cmd == "slice":
            for level in measure.parse_levels(str(q.get("z"))):
                c = level - shift[a]
                lo2, hi2 = [x - pad for x in lo], [x + pad for x in hi]
                lo2[a], hi2[a] = c - thin, c + thin
                gap = outside.min_gap(_solid_box(m3d, lo2, hi2), pad)
                if gap < MARGIN_MM:
                    return (f"{what} reads {part} at {axis} = {level:g}, where {part} goes on outside the section box "
                            f"(within {gap:.2f} mm of that plane; the section box must hold all of {part} within "
                            f"{MARGIN_MM:g} mm of it)")
            return None
        u_ax, v_ax = [i for i in range(3) if i != a]
        us, vs = measure.parse_range(str(q.get("u")), "--u"), measure.parse_range(str(q.get("v")), "--v")
        lo2, hi2 = [x - pad for x in lo], [x + pad for x in hi]
        for i, vals in ((u_ax, us), (v_ax, vs)):
            lo2[i], hi2[i] = min(vals) - shift[i] - thin, max(vals) - shift[i] + thin
        gap = outside.min_gap(_solid_box(m3d, lo2, hi2), pad)
        if gap < MARGIN_MM:
            return (f"{what} casts its rays across {part} where it goes on outside the section box (within "
                    f"{gap:.2f} mm of them; the section box must hold all of {part} within {MARGIN_MM:g} mm of them)")
        return None


def _swept_gap(sweep, near, mate, near_turns, margin):
    """The smallest gap between the part outside the box and the mating part through the turn the
    fit report swept (side b turns about the axis through the pivot, from its placed pose to the
    end of the range), checked at turns close enough that no point moves more than margin / 4
    between two, and returned less that quarter, so that it holds between them too. Returns
    (gap, None) or (None, why)."""
    import fit
    sweep = sweep if isinstance(sweep, dict) else {}
    axis, pivot, angles = sweep.get("axis"), sweep.get("pivot_mm"), sweep.get("angles_deg")
    if not (_vec3(axis) and _vec3(pivot) and isinstance(angles, list) and len(angles) == 2
            and all(finite(x) for x in angles)) or not any(axis):
        return None, "its sweep is not recorded as fit.py writes it, so the turn is not followed here"
    n = math.sqrt(sum(c * c for c in axis))
    axis = [c / n for c in axis]
    end = float(max(angles, key=abs))
    moving, fixed = (near, mate) if near_turns else (mate, near)
    step = margin / 4
    radius = fit.reach_radius(moving, axis, pivot)
    turns = max(1, math.ceil(math.radians(abs(end)) * radius / step)) if radius > 0 else 1
    if turns > SWEEP_TURNS:
        return None, f"its sweep needs {turns} turns to follow here, more than {SWEEP_TURNS}"
    gap = math.inf
    for i in range(turns + 1):
        deg = end * i / turns
        moved = moving.transform(fit.rotation_about(axis, pivot, deg)) if deg else moving
        gap = min(gap, fixed.min_gap(moved, margin + step + 1.0))
        if gap < margin:
            break
    return gap - step, None
