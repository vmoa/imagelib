#
# normalize.py -- canonical target name normalization
#
# Called at ingest time (via catalog.cname) so all new rows land with a
# consistent target name.  Also used by bin/migrate_targets.py to repair
# existing rows.
#
# Rule priority (applied in order):
#   1. Strip GCVS / GCVS5 catalog prefix
#   2. Messier, NGC, IC, HD pattern normalization
#   3. Sharpless, Barnard, Landolt pattern normalization
#   4. Explicit alias table for names that patterns cannot handle
#
# Catalogs intentionally left unchanged: SAC-prefixed objects, HIP, TYC,
# PGC, GSC, TIC, ASAS, WASP, Caldwell spelled-out, coordinate names,
# calibration frame names, and common proper names like "Bode's Galaxies".

import re

_ALIASES = {
    'dumbbell nebula':       'M 27',
    "Stephans' Quintet":     "Stephan's Quintet",
    'Pleiades Cluster':      'Pleiades',
    'Pleiades Star Cluster': 'Pleiades',
    'V1226 HER':             'V1226 Her',
    'v1226 her':             'V1226 Her',
    # After GCVS prefix is stripped, "GCVS alf 2 CVn" becomes "alf 2 CVn"
    'alf 2 CVn':             'Alpha 2 CVn',
}


def normalize_target(name):
    """Return the canonical form of a FITS target name.

    Returns the input unchanged when no rule or alias applies.
    """
    if not name:
        return name

    s = name.strip()

    # 1. Strip GCVS / GCVS5 catalog prefix
    s = re.sub(r'^GCVS5?\s+', '', s)

    # 2a. Messier: m27, M27, m 27 → M 27
    m = re.match(r'^[mM]\s*(\d+)$', s)
    if m:
        return 'M ' + m.group(1)

    # 2b. NGC: ngc 6946, NGC224 → NGC 6946, NGC 224
    m = re.match(r'^[nN][gG][cC]\s*(\d+)$', s)
    if m:
        return 'NGC ' + m.group(1)

    # 2c. IC: ic 434 → IC 434
    m = re.match(r'^[iI][cC]\s*(\d+)$', s)
    if m:
        return 'IC ' + m.group(1)

    # 2d. HD: HD225728 → HD 225728
    m = re.match(r'^HD\s*(\d+)$', s)
    if m:
        return 'HD ' + m.group(1)

    # 3a. Sharpless: Sh2-155, Sh2 222, Sh 2-155 → Sh 2-155, Sh 2-222
    m = re.match(r'^[Ss][Hh]\s*2[-\s]+(\d+)$', s)
    if m:
        return 'Sh 2-' + m.group(1)

    # 3b. Barnard dark nebula: B 70, B 72 → Barnard 70, Barnard 72
    #     Anchored full-string match avoids false matches on other B-prefixed IDs.
    m = re.match(r'^B\s+(\d+)$', s)
    if m:
        return 'Barnard ' + m.group(1)

    # 3c. Landolt standard star fields: SA 26 → SA26, SA 98 SF2 → SA98 SF2,
    #     SA32-Starfield → SA32
    m = re.match(r'^SA\s*(\d+)(?:\s+SF(\d+)|-Starfield)?$', s)
    if m:
        if m.group(2):
            return 'SA' + m.group(1) + ' SF' + m.group(2)
        return 'SA' + m.group(1)

    # 4. Explicit aliases
    return _ALIASES.get(s, s)
