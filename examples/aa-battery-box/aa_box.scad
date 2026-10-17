// AA battery box with slip-on lid — generated with 3dprint-scout
// Print orientation: box opening up; lid printed top-down (opening up). Z = 0 is the bed.

// PARAMETERS (mm) ------------------------------------------------------------
cell_d       = 14.5;  // AA (LR6) max diameter — Panasonic LR6XW spec; Adafruit AA datasheet (GB/T 8897 = IEC 60086)
cell_h       = 50.5;  // AA max height — same two sources
pocket_clear = 0.3;   // radial, per side: object in a pocket (tolerances.md). Hole compensation is the slicer's job.
cols         = 4;
rows         = 2;
rib          = 1.6;   // between pockets
wall         = 3.0;   // outer wall; leaves 1.4 at the lip
floor_t      = 1.6;
pocket_depth = 32;    // cells stick out (cell_h - pocket_depth) so they can be pinched
lip_h        = 6;     // height of the stepped-in lip the lid slides over
lip_inset    = 1.6;   // how far the lip steps in from the outer wall
slide        = 0.2;   // radial, per side: sliding fit (tolerances.md)
lid_top      = 1.6;
headroom     = 0.5;   // gap between cell tops and the lid ceiling
part         = "box"; // set by build.py: "box" or "lid"
$fa = 1; $fs = 0.4;

// DERIVED --------------------------------------------------------------------
pocket_d = cell_d + 2 * pocket_clear;
pitch    = pocket_d + rib;
W        = cols * pocket_d + (cols - 1) * rib + 2 * wall;
D        = rows * pocket_d + (rows - 1) * rib + 2 * wall;
box_h    = floor_t + pocket_depth;
lid_in_w = W - 2 * lip_inset + 2 * slide;
lid_in_d = D - 2 * lip_inset + 2 * slide;
lid_in_h = lip_h + (cell_h - pocket_depth) + headroom;
lid_h    = lid_in_h + lid_top;

assert(wall - lip_inset >= 1.2 - 1e-6, "box wall at the lip is thinner than 1.2 mm");
assert((W - lid_in_w) / 2 >= 1.2 - 1e-6, "lid wall is thinner than 1.2 mm");
assert(rib >= 1.2 - 1e-6, "rib between pockets is thinner than 1.2 mm");

// MODEL ----------------------------------------------------------------------
module box() {
  difference() {
    union() {
      cube([W, D, box_h - lip_h]);
      translate([lip_inset, lip_inset, 0]) cube([W - 2 * lip_inset, D - 2 * lip_inset, box_h]);
    }
    for (i = [0 : cols - 1], j = [0 : rows - 1])
      translate([wall + pocket_d / 2 + i * pitch, wall + pocket_d / 2 + j * pitch, floor_t])
        cylinder(d = pocket_d, h = box_h);   // ends above the top: overshoot
  }
}

module lid() {
  difference() {
    cube([W, D, lid_h]);
    translate([(W - lid_in_w) / 2, (D - lid_in_d) / 2, lid_top]) cube([lid_in_w, lid_in_d, lid_h]);
  }
}

if (part == "box") box();
if (part == "lid") lid();
