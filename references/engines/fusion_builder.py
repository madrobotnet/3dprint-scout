"""
fusion_builder.py - a Builder for Fusion generator scripts sent through an MCP execute tool.

Paste the whole file above your `def run(context=None):` (or exec it from a file after an md5
check, fusion.md "Sending scripts"). It wraps the handful of Fusion API calls a parametric
part needs: user parameters that drive the features, sketches with real circles and arcs,
extrude / revolve, right-handed frames to move bodies, join / cut that refuse a tool that
does not touch its target and report leftovers, one STL per named body, and a JSON summary.

Units: the Fusion API works in centimetres; every number this file takes or prints is mm.
Expressions ("p_w / 2 - p_wall") are passed to Fusion as strings and stay live, so editing a
parameter in Fusion's Change Parameters dialog rebuilds the model.

    PARAMS = {"w": 60.0, "d": 40.0, "h": 25.0, "wall": 2.0}

    def run(context=None):
        app = adsk.core.Application.get()
        design = adsk.fusion.Design.cast(app.activeProduct)
        B = Builder(design)
        B.clear()                                   # rebuild from scratch every run
        P = B.params(PARAMS)                        # {"w": "p_w", ...}: user parameters in mm
        sk = B.sketch("outer")
        B.rect(sk, 0, 0, PARAMS["w"], PARAMS["d"], w_expr=P["w"], d_expr=P["d"])
        body = B.extrude(sk, 0, P["h"], "body")     # z0, z1: mm numbers or expressions
        sk2 = B.sketch("pocket")
        B.rect(sk2, 2, 2, PARAMS["w"] - 4, PARAMS["d"] - 4)
        B.extrude(sk2, P["wall"], P["h"] + " + 1", "pocket", operation="cut", target=body)
        print(B.export(r"C:\\path\\to\\out", ["body"]))  # one STL per body, JSON summary

Derived from the Builder that ran in the 2026-10-17 field test (X2D exhaust adapter); this
cleaned version has not yet been run in Fusion. Pure-Python helpers (frames, parameter names,
box overlap, the summary) are unit-tested; the API calls are checked against the Fusion API
reference only.
"""
import json
import math
import os

try:
    import adsk.core
    import adsk.fusion
except ImportError:                     # outside Fusion (tests, syntax check): helpers still work
    adsk = None

PREFIX = "p_"                           # user parameter prefix; keep names unique per design


# --------------------------------------------------------------------------- #
# Pure helpers (no Fusion needed)
# --------------------------------------------------------------------------- #
def cm(mm_value):
    """mm -> cm, the unit of the Fusion API."""
    return float(mm_value) / 10.0


def mm(cm_value):
    """cm (as read back from the API) -> mm."""
    return float(cm_value) * 10.0


def param_name(key, prefix=PREFIX):
    """Fusion user-parameter name for a params.json key: prefix + key, letters, digits and
    underscores only, not starting with a digit. Raises ValueError otherwise."""
    name = f"{prefix}{key}"
    if not name or not (name[0].isalpha() or name[0] == "_") or not all(c.isalnum() or c == "_" for c in name):
        raise ValueError(f"'{key}' is not a usable parameter name (letters, digits, underscores)")
    return name


def expression(value, unit="mm"):
    """A number becomes '<value> mm'; a string is an expression and is passed as is."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{value!r} is not a length or an expression")
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError(f"{value!r} is not a finite length")
        return f"{value} {unit}"
    return str(value)


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    if n < 1e-12:
        raise ValueError("zero-length axis")
    return tuple(c / n for c in v)


def right_handed(x_axis, y_axis):
    """Unit (x, y, z) with z = x × y, so the frame is right-handed. Raises ValueError when x and
    y are parallel or not perpendicular: a left-handed or skewed Matrix3D broke a feature in the
    field test, and Fusion does not warn."""
    x, y = _unit(x_axis), _unit(y_axis)
    if abs(sum(a * b for a, b in zip(x, y))) > 1e-6:
        raise ValueError(f"axes are not perpendicular: x={x_axis}, y={y_axis}")
    z = (x[1] * y[2] - x[2] * y[1], x[2] * y[0] - x[0] * y[2], x[0] * y[1] - x[1] * y[0])
    return x, y, z


def box_of(body):
    """{"min": [mm], "max": [mm], "size": [mm]} of a BRepBody (API box is in cm)."""
    bb = body.boundingBox
    lo = [mm(bb.minPoint.x), mm(bb.minPoint.y), mm(bb.minPoint.z)]
    hi = [mm(bb.maxPoint.x), mm(bb.maxPoint.y), mm(bb.maxPoint.z)]
    return {"min": [round(v, 3) for v in lo], "max": [round(v, 3) for v in hi],
            "size": [round(h - l, 3) for l, h in zip(lo, hi)]}


def boxes_touch(a, b, margin=0.01):
    """True when two {"min", "max"} boxes (mm) overlap or touch within `margin` mm. A join or
    cut whose tool is farther away than this does nothing and leaves the tool body behind."""
    return all(a["min"][i] <= b["max"][i] + margin and b["min"][i] <= a["max"][i] + margin for i in range(3))


def summary(bodies_info, folder=None):
    """JSON text for the agent: bodies with boxes, volumes and STL sizes."""
    return json.dumps({"schema": "3dprint-scout.fusion_builder/1", "folder": folder, "bodies": bodies_info},
                      indent=1, sort_keys=True)


# --------------------------------------------------------------------------- #
# Builder (needs Fusion)
# --------------------------------------------------------------------------- #
class Builder:
    def __init__(self, design, prefix=PREFIX, comment="3dprint-scout"):
        if adsk is None:
            raise RuntimeError("fusion_builder.Builder runs inside Fusion only")
        self.design = design
        self.root = design.rootComponent
        self.prefix = prefix
        self.comment = comment
        self.names = {}                 # params.json key -> user parameter name

    # ----- housekeeping ---------------------------------------------------- #
    def clear(self):
        """Delete every timeline entity, last first, so each run rebuilds from scratch."""
        tl = self.design.timeline
        for i in range(tl.count - 1, -1, -1):
            ent = tl.item(i).entity
            if ent is not None and ent.isValid:
                ent.deleteMe()

    def params(self, values):
        """Create or update one user parameter per entry (mm). Returns {key: parameter name}:
        use the names in expressions so the features follow the parameters."""
        ups = self.design.userParameters
        for key, value in values.items():
            name = param_name(key, self.prefix)
            expr = expression(value)
            par = ups.itemByName(name)
            if par:
                par.expression = expr
            else:
                ups.add(name, adsk.core.ValueInput.createByString(expr), "mm", self.comment)
            self.names[key] = name
        return dict(self.names)

    def value(self, v):
        """ValueInput from a number (mm) or an expression string."""
        return adsk.core.ValueInput.createByString(expression(v))

    def bodies(self):
        """{name: BRepBody} of the root component."""
        return {b.name: b for b in (self.root.bRepBodies.item(i) for i in range(self.root.bRepBodies.count))}

    # ----- sketches (mm; real circles and arcs, never polylines) ----------- #
    def sketch(self, name, plane=None):
        sk = self.root.sketches.add(plane or self.root.xYConstructionPlane)
        sk.name = name
        return sk

    def _pt(self, x, y):
        return adsk.core.Point3D.create(cm(x), cm(y), 0)

    def polygon(self, sk, points):
        """Closed polyline through (x, y) mm points. For round shapes use circle / rounded_rect."""
        if len(points) < 3:
            raise ValueError("a polygon needs at least three points")
        lines = sk.sketchCurves.sketchLines
        pts = [self._pt(x, y) for x, y in points]
        first = lines.addByTwoPoints(pts[0], pts[1])
        prev = first
        for p in pts[2:]:
            prev = lines.addByTwoPoints(prev.endSketchPoint, p)
        lines.addByTwoPoints(prev.endSketchPoint, first.startSketchPoint)
        return first

    def rect(self, sk, x0, y0, w, d, w_expr=None, d_expr=None):
        """Rectangle with its corner at (x0, y0). With w_expr / d_expr (parameter names or
        expressions) the width and depth get sketch dimensions driven by them."""
        lines = sk.sketchCurves.sketchLines.addTwoPointRectangle(self._pt(x0, y0), self._pt(x0 + w, y0 + d))
        if w_expr or d_expr:
            dims = sk.sketchDimensions
            # Pick the sides by geometry, not by index: the API does not promise an order.
            items = [lines.item(i) for i in range(lines.count)]

            def ends(line):
                return line.startSketchPoint.geometry, line.endSketchPoint.geometry
            bottom = min((ln for ln in items if abs(ends(ln)[0].y - ends(ln)[1].y) < 1e-9), key=lambda ln: ends(ln)[0].y)
            right = max((ln for ln in items if abs(ends(ln)[0].x - ends(ln)[1].x) < 1e-9), key=lambda ln: ends(ln)[0].x)
            if w_expr:
                dim = dims.addDistanceDimension(bottom.startSketchPoint, bottom.endSketchPoint,
                                                adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation,
                                                self._pt(x0 + w / 2, y0 - 5))
                dim.parameter.expression = expression(w_expr)
            if d_expr:
                dim = dims.addDistanceDimension(right.startSketchPoint, right.endSketchPoint,
                                                adsk.fusion.DimensionOrientations.VerticalDimensionOrientation,
                                                self._pt(x0 + w + 5, y0 + d / 2))
                dim.parameter.expression = expression(d_expr)
        return lines

    def circle(self, sk, cx, cy, r, d_expr=None):
        """A real circle (no polyline). d_expr drives the diameter."""
        c = sk.sketchCurves.sketchCircles.addByCenterRadius(self._pt(cx, cy), cm(r))
        if d_expr:
            dim = sk.sketchDimensions.addDiameterDimension(c, self._pt(cx + r, cy + r))
            dim.parameter.expression = expression(d_expr)
        return c

    def rounded_rect(self, sk, x0, y0, w, d, r):
        """Rectangle with four real quarter-circle corners of radius r."""
        if r <= 0 or 2 * r > min(w, d):
            raise ValueError(f"corner radius {r} does not fit a {w} x {d} rectangle")
        lines, arcs = sk.sketchCurves.sketchLines, sk.sketchCurves.sketchArcs
        x1, y1 = x0 + w, y0 + d
        # Edges, counter-clockwise, then an arc at every corner from the end of one edge to the start of the next.
        edges = [lines.addByTwoPoints(self._pt(x0 + r, y0), self._pt(x1 - r, y0)),
                 lines.addByTwoPoints(self._pt(x1, y0 + r), self._pt(x1, y1 - r)),
                 lines.addByTwoPoints(self._pt(x1 - r, y1), self._pt(x0 + r, y1)),
                 lines.addByTwoPoints(self._pt(x0, y1 - r), self._pt(x0, y0 + r))]
        centres = [(x1 - r, y0 + r), (x1 - r, y1 - r), (x0 + r, y1 - r), (x0 + r, y0 + r)]
        for i, (ccx, ccy) in enumerate(centres):
            start = edges[i].endSketchPoint
            arcs.addByCenterStartSweep(self._pt(ccx, ccy), start, math.pi / 2)
        return edges

    # ----- features -------------------------------------------------------- #
    def _profiles(self, sk):
        coll = adsk.core.ObjectCollection.create()
        for i in range(sk.profiles.count):
            coll.add(sk.profiles.item(i))
        if coll.count == 0:
            raise ValueError(f"sketch '{sk.name}' has no closed profile")
        return coll

    def extrude(self, sk, z0, z1, name, operation="new", target=None):
        """Extrude every closed profile of the sketch from z0 to z1 (mm numbers or expressions):
        a sketch with an inner loop gives the outer ring AND the inner disk, so draw holes in
        their own sketch and cut them. operation: new (returns the body, named), join / cut /
        intersect (into target)."""
        ops = {"new": adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
               "join": adsk.fusion.FeatureOperations.JoinFeatureOperation,
               "cut": adsk.fusion.FeatureOperations.CutFeatureOperation,
               "intersect": adsk.fusion.FeatureOperations.IntersectFeatureOperation}
        if operation not in ops:
            raise ValueError(f"operation must be one of {sorted(ops)}")
        if operation != "new" and target is None:
            raise ValueError(f"extrude '{name}': {operation} needs a target body")
        inp = self.root.features.extrudeFeatures.createInput(self._profiles(sk), ops[operation])
        inp.startExtent = adsk.fusion.OffsetStartDefinition.create(self.value(z0))
        if isinstance(z0, (int, float)) and isinstance(z1, (int, float)):
            distance = z1 - z0
        else:
            distance = f"({expression(z1)}) - ({expression(z0)})"
        inp.setDistanceExtent(False, self.value(distance))
        if target is not None:
            inp.participantBodies = [target]
        feat = self.root.features.extrudeFeatures.add(inp)
        if operation != "new":
            return target
        bodies = [feat.bodies.item(i) for i in range(feat.bodies.count)]
        if not bodies:
            raise ValueError(f"extrude '{name}' produced no body")
        body = bodies[0]
        if len(bodies) > 1:
            body = self.join(body, bodies[1:])
        body.name = name
        return body

    def revolve(self, sk, axis_line, name, angle_deg=360.0):
        """Revolve the sketch's first profile about a sketch line (make it construction)."""
        axis_line.isConstruction = True
        inp = self.root.features.revolveFeatures.createInput(
            sk.profiles.item(0), axis_line, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        inp.setAngleExtent(False, adsk.core.ValueInput.createByReal(math.radians(angle_deg)))
        feat = self.root.features.revolveFeatures.add(inp)
        body = feat.bodies.item(0)
        body.name = name
        return body

    def frame(self, origin, x_axis, y_axis):
        """Matrix3D placing local axes at origin (mm); z = x × y so it is always right-handed."""
        x, y, z = right_handed(x_axis, y_axis)
        m = adsk.core.Matrix3D.create()
        m.setWithCoordinateSystem(adsk.core.Point3D.create(cm(origin[0]), cm(origin[1]), cm(origin[2])),
                                  adsk.core.Vector3D.create(*x), adsk.core.Vector3D.create(*y),
                                  adsk.core.Vector3D.create(*z))
        return m

    def move(self, bodies, matrix):
        coll = adsk.core.ObjectCollection.create()
        for b in bodies:
            coll.add(b)
        mf = self.root.features.moveFeatures
        inp = mf.createInput2(coll)
        inp.defineAsFreeMove(matrix)
        mf.add(inp)

    def _combine(self, target, tools, op, what):
        tbox = box_of(target)
        for t in tools:
            if not boxes_touch(tbox, box_of(t)):
                raise ValueError(f"{what}: tool '{t.name}' does not touch target '{target.name}' "
                                 f"(boxes {box_of(t)['min']}..{box_of(t)['max']} vs {tbox['min']}..{tbox['max']}); "
                                 "Fusion would leave the tool body behind")
        names = [t.name for t in tools]
        coll = adsk.core.ObjectCollection.create()
        for t in tools:
            coll.add(t)
        cf = self.root.features.combineFeatures
        inp = cf.createInput(target, coll)
        inp.operation = op
        inp.isKeepToolBodies = False
        cf.add(inp)
        leftover = [n for n in names if n in self.bodies()]
        if leftover:
            raise ValueError(f"{what}: tool bodies {leftover} are still there after the combine; "
                             "they did not intersect the target")
        return target

    def join(self, target, tools):
        return self._combine(target, tools, adsk.fusion.FeatureOperations.JoinFeatureOperation, "join")

    def cut(self, target, tools):
        return self._combine(target, tools, adsk.fusion.FeatureOperations.CutFeatureOperation, "cut")

    # ----- export ---------------------------------------------------------- #
    def export(self, folder, names=None, refinement="high"):
        """One binary STL per body (name.stl) at the given refinement into `folder`, plus a
        summary.json. Returns the summary text; print it so the agent gets the numbers."""
        os.makedirs(folder, exist_ok=True)
        bodies = self.bodies()
        names = list(names) if names else sorted(bodies)
        missing = [n for n in names if n not in bodies]
        if missing:
            raise ValueError(f"no body named {missing}; bodies are {sorted(bodies)}")
        em = self.design.exportManager
        info = {}
        for n in names:
            b = bodies[n]
            path = os.path.join(folder, n + ".stl")
            opt = em.createSTLExportOptions(b, path)
            opt.meshRefinement = getattr(adsk.fusion.MeshRefinementSettings, "MeshRefinement" + refinement.capitalize())
            opt.isBinaryFormat = True
            em.execute(opt)
            entry = box_of(b)
            entry["volume_mm3"] = round(b.volume * 1000.0, 1)          # cm3 -> mm3
            entry["stl"] = path
            entry["bytes"] = os.path.getsize(path)
            info[n] = entry
        text = summary(info, folder)
        with open(os.path.join(folder, "summary.json"), "w", encoding="utf-8") as f:
            f.write(text)
        return text
