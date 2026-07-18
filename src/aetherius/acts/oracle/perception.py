"""Oracle perception is the shared browser perception (see ``acts/_perception.py``).

Oracle reuses Continuum's open page and the shared ``capture()``; no separate perception exists.
This module remains the Act's seam for any Oracle-specific screenshot pre-processing (e.g.
cropping to a region before grounding), should one become necessary.
"""
