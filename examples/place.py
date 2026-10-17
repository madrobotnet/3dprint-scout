"""Rotate and move a copy of an STL, so preview.py can draw parts side by side or assembled.

    python3 ../place.py out/lid.stl out/lid_placed.stl --rotate 180,0,0 --translate 0,45,33

Rotation (degrees about X, then Y, then Z) is applied before translation (mm), the same
convention as fit.py's --b-rotate and --b-translate. Needs manifold3d and numpy.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import manifold3d as m3d  # noqa: E402
from build import write_binary_stl  # noqa: E402
from fit import _vec, load_part, place  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("stl")
ap.add_argument("out")
ap.add_argument("--rotate", default="0,0,0", help="rx,ry,rz degrees")
ap.add_argument("--translate", default="0,0,0", help="x,y,z mm")
args = ap.parse_args()

man = place(load_part(args.stl, m3d), _vec(args.rotate, "--rotate"), _vec(args.translate, "--translate"))
mesh = man.to_mesh()
write_binary_stl(args.out, [tuple(map(float, v[:3])) for v in mesh.vert_properties],
                 [tuple(map(int, t)) for t in mesh.tri_verts])
print(args.out)
