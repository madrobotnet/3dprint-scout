"""Proxy of the USB-C plug head (never printed or delivered): a box of the plug's sizes, every
one from its own params file (.3dprint/usb_c_plug.json, the numbers of dims usb-c-plug). fit.py
places it between the prongs, its top at the prong top where the phone's bottom rests."""
import manifold3d as m3d


def build(p):
    return {"plug": m3d.Manifold.cube([p["plug_w"], p["plug_h"], p["plug_l"]])}
