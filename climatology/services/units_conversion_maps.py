"""SIGRID-3 unit conversion maps for CIS sea-ice data.

Encoding tables and parsers that convert categorical SIGRID-3 codes to
numeric values. The internal representation across the project is
**fraction** (range [0, 1]) for concentrations; display layers handle
percentage formatting where appropriate.

Source: SIGRID-3 v3.1 documentation (2010) and the 2004 CIS convention.
Tables are intentionally restricted to codes actually observed in the
local SGRDA archive (backend/probes/003_concentration_census). Spec
codes never seen in the data are omitted so that any future encounter
surfaces as a loud KeyError rather than being silently mapped.
"""

from __future__ import annotations

# Concentration code -> fraction in [0, 1].
# Includes only codes observed in probe 003 (SGRDA) and in sgrdr (CT census,
# 2026-06-10, during clim-008).
CONCENTRATION_FRACTION: dict[str, float] = {
    "00": 0.00,   # ice-free (2004 convention; 2010 code "55" not observed)
    "98": 0.00,   # ice-free — SGRDR encoding, exclusively on POLY_TYPE='W'
                  # polygons (3 327/3 736 W rows, 1968–2020; never on ice
                  # polygons; absent from SGRDA). User-confirmed 2026-06-10.
    "01": 0.04,   # bergy water / <1/10 — per "Open water/bergy water < 1 tenth"; confirmed 0.04 (DEC-043)
    "02": 0.04,   # bergy water variant — trace value 0.04 confirmed (DEC-043)
    "10": 0.10,
    "20": 0.20,
    "30": 0.30,
    "40": 0.40,
    "50": 0.50,
    "60": 0.60,
    "70": 0.70,
    "80": 0.80,
    "90": 0.90,
    "91": 0.97,   # "9+/10" — DEC-015: adopt the CIS-documented value 9.7/10 (0.97) for the
                  # "9+" code (CIS Archive No.1; reading-log e060), which the doc states differs
                  # from the 10/10 implied by summing partials. Changed 2026-06-09 from 1.00.
                  # (Probe 001 found CT='91' partials sum to 1.0 across 20 613 SGRDA rows, which
                  # had motivated the prior 1.00; the CIS documentation is now treated as
                  # authoritative over that indirect inference.)
    "92": 1.00,   # compact (10/10) — genuine full coverage, distinct from "9+"; unchanged.
}

# Codes treated as missing data (SIGRID-3 dummy variable convention).
# '9-' is treated as a typo of '-9' (12 occurrences in CB/CC per probe 003).
MISSING_CODES: frozenset[str] = frozenset({"-9", "9-"})

# Documented data-entry typos with silent substitution.
# Probe 003: 4 rows of "8" and 2 rows of "9" in CA. Assumed to be typos
# of "80" and "90" respectively, consistent with the 2-digit SIGRID-3
# encoding and the surrounding-row context.
_TYPO_SUBSTITUTIONS: dict[str, str] = {
    "8": "80",
    "9": "90",
}


def parse_concentration(code: str | None) -> float | None:
    """Parse a SIGRID-3 concentration code to a fraction in [0, 1].

    Returns
    -------
    float in [0, 1] for known codes.
    None for missing/dummy values (``-9``, ``9-``, empty, ``None``).

    Raises
    ------
    KeyError for codes that are neither in the table nor recognised as
    missing or typo. This is intentional: novel codes should surface as
    failures rather than being silently coerced.
    """
    if code is None or code == "" or code in MISSING_CODES:
        return None
    canonical = _TYPO_SUBSTITUTIONS.get(code, code)
    try:
        return CONCENTRATION_FRACTION[canonical]
    except KeyError as e:
        raise KeyError(f"Unrecognised SIGRID-3 concentration code: {code!r}") from e


# Stage-of-development code -> midpoint ice thickness in metres.
# Data-driven: only codes observed in probe 002 are encoded.
# - Range codes use the midpoint of the SIGRID-3 v3.1 thickness range.
# - Code 93 ("Thick First Year Ice, >=120 cm") uses 160 cm (midpoint of 120-200,
#   bounded by First Year Ice's broad 30-200 cm upper limit).
# - Codes 95-97 (Old/Second Year/Multi-Year Ice): confirmed same thickness
#   family as code 93 (Thick FYI) → 1.600 m (Brad Drummond/CIS, pers.
#   comm. 2026-06-25, DEC-043).
# - Codes 98 (Glacier Ice) and 99 (Undetermined): None — excluded by
#   methodology; ice of land origin and undetermined stages are not included
#   in volume climatology (DEC-043).
STAGE_OF_DEVELOPMENT_THICKNESS: dict[str, float | None] = {
    # Stages with defined thickness ranges
    "81": 0.050,   # New Ice                       (<10 cm)
    "84": 0.125,   # Grey Ice                      (10-15 cm)
    "85": 0.225,   # Grey-White Ice                (15-30 cm)
    "86": 1.150,   # First Year Ice (broad)        (30-200 cm)
    "87": 0.500,   # Thin First Year Ice           (30-70 cm)
    "91": 0.950,   # Medium First Year Ice         (70-120 cm)
    "93": 1.600,   # Thick First Year Ice          (>=120 cm; midpoint 120-200)
    "95": 1.600,   # Old Ice          — same family as code 93 (DEC-043)
    "96": 1.600,   # Second Year Ice  — same family as code 93 (DEC-043)
    "97": 1.600,   # Multi-Year Ice   — same family as code 93 (DEC-043)
    # Methodological exclusion: ice of land origin and undetermined stages
    # are not included in volume climatology (DEC-043).
    "98": None,    # Glacier Ice
    "99": None,    # Undetermined / Unknown
}

# Stage codes treated as encoding errors. Observed in <10 rows total across
# the local SGRDA archive (probe 002), all outside the SIGRID-3 v3.1 valid
# code set. Silently mapped to None to avoid log noise on a static DB.
# Their occurrence is tracked in probe 002 output for future audit.
INVALID_STAGE_CODES: frozenset[str] = frozenset({"7C", "9C", "5-", "6-", "10", "50"})


def parse_stage_thickness(code: str | None) -> float | None:
    """Parse a SIGRID-3 stage-of-development code to ice thickness in metres.

    Returns
    -------
    float (metres) for known stages with a defined thickness range.
    None for: missing/dummy values (``-9``, ``9-``, empty, ``None``),
    encoding errors in :data:`INVALID_STAGE_CODES`, and stages excluded
    by methodology (`98` Glacier Ice, `99` Undetermined — ice of land
    origin and undetermined stages not included in volume climatology,
    DEC-043).

    Raises
    ------
    KeyError for codes that are neither in the table nor recognised as
    missing or invalid. Surfacing novelty loudly is intentional on a
    static archive: any new code is information.
    """
    if code is None or code == "" or code in MISSING_CODES:
        return None
    if code in INVALID_STAGE_CODES:
        return None
    try:
        return STAGE_OF_DEVELOPMENT_THICKNESS[code]
    except KeyError as e:
        raise KeyError(f"Unrecognised SIGRID-3 stage-of-development code: {code!r}") from e


# Convenience: subset of stages observed in data that have no defined thickness.
# Useful for downstream "volume loss" estimates and explicit skipping rules.
NO_THICKNESS_STAGE_CODES: frozenset[str] = frozenset(
    code for code, t in STAGE_OF_DEVELOPMENT_THICKNESS.items() if t is None
)
