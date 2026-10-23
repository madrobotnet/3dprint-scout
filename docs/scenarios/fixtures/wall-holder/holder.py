"""Wall-mounted phone charging holder: a back plate taped to the wall and two prongs the phone
stands on, each with a front lip; the charging plug and its cable pass down between the prongs.
Modelled in the print orientation, which is also the use orientation: the back plate stands on
its bottom edge, the prongs lie on the bed and point forward (+Y)."""
import manifold3d as m3d

# Every size in mm; params.json overrides by key.
DEFAULTS = {
    "phone_t": 11.0,       # phone in its case, thickness (dims phone-case: the user's caliper)
    "seat_clear": 1.0,     # gap in front of the phone in the seat, total (tolerances.md: object in a pocket)
    "base_t": 6.0,         # prong thickness (strength member "prong": h)
    "prong_w": 18.0,       # width of each prong (strength member "prong": b)
    "base_d": 15.0,        # prong length from the back plate (strength member "prong": length)
    "base_support": "cantilever",  # the prongs hang off the back plate
    "base_orient": "xy",   # the prongs lie on the bed: the bending stress stays in the layer plane
    "notch_w": 13.0,       # gap between the prongs where the plug and its cable pass down
    "lip_t": 3.0,          # front lip, depth
    "lip_h": 7.0,          # front lip, height above the prong top
    "back_t": 4.0,         # back plate thickness
    "back_h": 70.0,        # back plate height (the double-sided tape goes on its back)
    "plug_w": 12.0,        # USB-C plug head, width (dims usb-c-plug; plug.py builds the proxy from them)
    "plug_h": 6.5,         # USB-C plug head, thickness
    "plug_l": 22.0,        # USB-C plug head with its strain relief, length
}


def build(params):
    p = {**DEFAULTS, **params}
    if p["base_d"] < p["phone_t"] + p["seat_clear"] + p["lip_t"]:
        raise ValueError("base_d is shorter than the phone, the seat gap and the lip together")
    width = 2 * p["prong_w"] + p["notch_w"]
    body = m3d.Manifold.cube([width, p["back_t"], p["back_h"]])
    for x in (0.0, p["prong_w"] + p["notch_w"]):
        prong = m3d.Manifold.cube([p["prong_w"], p["base_d"], p["base_t"]]).translate([x, p["back_t"], 0])
        lip = m3d.Manifold.cube([p["prong_w"], p["lip_t"], p["lip_h"]]).translate(
            [x, p["back_t"] + p["base_d"] - p["lip_t"], p["base_t"]])
        body = body + prong + lip
    return {"holder": body}
