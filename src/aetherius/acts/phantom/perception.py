"""Phantom perception is the shared browser perception plus fusion (see ``acts/_perception.py``).

Phantom perceives via the shared ``capture()`` (screenshot + geometry) and may fuse the DOM and the
accessibility tree into the planner state. Kept as the Act's seam for that fusion, added in Jalon
2-D; no separate browser is launched.
"""
