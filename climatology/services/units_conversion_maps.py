"""
SIGRID-3 unit conversion maps for CIS sea-ice data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


# Uniform CIS trace concentration (DEC-044). Equals map('92') - map('91').
TRACE_CONCENTRATION: float = 0.03


# Codes observed in probe 003
# See /docs/normative/SIGRID and CIS for more details
CONCENTRATION_FRACTION: dict[str, float] = {
    "00": 0.00,
    "98": 0.00,
    "01": TRACE_CONCENTRATION,
    "02": TRACE_CONCENTRATION,
    "10": 0.10,
    "20": 0.20,
    "30": 0.30,
    "40": 0.40,
    "50": 0.50,
    "60": 0.60,
    "70": 0.70,
    "80": 0.80,
    "90": 0.90,
    "91": 0.97,  
    "92": 1.00, 
}

# Codes treated as missing data (see probe 003).
MISSING_CODES: frozenset[str] = frozenset({"-9", "9-"})

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


# Form-of-ice code -> representative floe diameter in metres (midpoint of the
# SIGRID-3 size range). Source: SIGRID-3 2010 rev2 Table 4.3 — the
# CIS-authoritative table; the 2017 v3.1 renumbering is deliberately NOT used
# (it shifts Fast Ice 08->09, which would mis-encode the dominant CIS form).
# Data-driven: only codes observed in probe 018 are encoded. None = no defined
# floe class (fast ice is continuous; icebergs/undetermined carry no floe size).
# DEC-045.
FORM_SIZES: dict[str, float | None] = {
    "01": 1.0,       # Shuga/Small Ice Cake, Brash Ice  (<2 m,  midpoint 0-2)
    "02": 10.0,      # Ice Cake                         (<20 m, midpoint 0-20)
    "03": 60.0,      # Small Floe                       (20-100 m)
    "04": 300.0,     # Medium Floe                      (100-500 m)
    "05": 1250.0,    # Big Floe                         (500 m-2 km)
    "06": 6000.0,    # Vast Floe                        (2-10 km)
    "07": 10000.0,   # Giant Floe (>10 km) — provisional lower bound, PENDING CIS
    "08": None,      # Fast Ice — continuous attached ice, no floe size
    "10": None,      # Icebergs — no floe class
    "99": None,      # Undetermined / Unknown
}

# Form codes treated as encoding errors. Observed in 18 rows total across the
# SGRDA archive (probe 018), all C-suffixed and outside the SIGRID-3 form set.
# Silently mapped to None to avoid log noise on a static DB; tracked in probe
# 018 output for future audit. Mirrors INVALID_STAGE_CODES.
INVALID_FORM_CODES: frozenset[str] = frozenset({"2C", "5C", "9C"})


def parse_form_size(code: str | None) -> float | None:
    """Parse a SIGRID-3 form-of-ice code to a representative floe diameter in metres.

    Returns
    -------
    float (metres) for known forms with a defined floe-size range.
    None for: missing/dummy values (``-9``, ``9-``, empty, ``None``), encoding
    errors in :data:`INVALID_FORM_CODES`, and forms with no floe class
    (``08`` Fast Ice, ``10`` Icebergs, ``99`` Undetermined).

    Raises
    ------
    KeyError for codes that are neither in the table nor recognised as missing
    or invalid — novel codes surface loudly on this static archive (DEC-045).
    """
    if code is None or code == "" or code in MISSING_CODES:
        return None
    if code in INVALID_FORM_CODES:
        return None
    try:
        return FORM_SIZES[code]
    except KeyError as e:
        raise KeyError(f"Unrecognised SIGRID-3 form-of-ice code: {code!r}") from e


# --- Per-polygon volume attribution (DEC-029/044) --------------------------
# Regime-aware decomposition of one polygon's SIGRID-3 codes into per-slot
# concentration x thickness — the single source of truth shared by the raw
# netCDF product (disaggregated bands) and the future volume metric (the
# concentration-weighted thickness sum). Probe 004 enumerated the column
# signatures; DEC-029/043/044 fixed the attribution rules.

# Ice-description slots of a SIGRID-3 egg: O (SO trace), A/B/C (named partials),
# D (SD remaining class). CN is the SO stage code and CD the SD stage code — both
# are stage-of-development codes, not concentrations (the CN/CD naming quirk;
# see CLAUDE.md), so they map through STAGE_OF_DEVELOPMENT_THICKNESS.
SLOTS: tuple[str, ...] = ("O", "A", "B", "C", "D")


def _present(code: str | None) -> bool:
    """True if a SIGRID-3 code carries information (not None/empty/missing)."""
    return code is not None and code != "" and code not in MISSING_CODES


@dataclass(frozen=True)
class PolygonAttribution:
    """Per-slot concentration + thickness for one polygon (DEC-029).

    ``ct`` is the total concentration (fraction). ``conc[slot]`` is the fraction
    attributed to each ice-description slot O/A/B/C/D and ``thk[slot]`` its
    midpoint thickness in metres (None where the stage has no defined thickness
    — e.g. 98/99 — or no stage code is present for the slot).
    ``volume_per_area`` is ``CT × Σ(conc·thk)/Σ(conc)`` (metres of ice-equivalent)
    — the ice-covered fraction times the concentration-weighted mean thickness,
    normalized by Σ conc since the partials can sum past CT (DEC-044); multiply
    by a cell's ground area for ice volume.
    """

    ct: float
    conc: dict[str, float]
    thk: dict[str, float | None]

    @property
    def volume_per_area(self) -> float:
        slots = [s for s in SLOTS if self.thk[s] is not None]
        denom = sum(self.conc[s] for s in slots)
        if denom == 0.0:
            return 0.0
        mean_thk = sum(self.conc[s] * self.thk[s] for s in slots) / denom
        return self.ct * mean_thk


def _sd_concentration(*, ct_eff: float, ca: float | None, cb: float | None,
                      cc: float | None, single_stage: bool) -> float:
    """SD (slot D) concentration via the DEC-044 CT_eff-reconciled residual rule.

    Single-stage -> trace. Multi-stage -> residual ``r = CT_eff - (CA+CB+CC)``,
    where ``CT_eff`` reconciles the '9+' encoding (CT='91') to full coverage 1.0
    (probe 001: partials max out at 1.0, not 0.97). Reconciliation removes the
    old -0.03 benign band, so ``r == 0`` -> trace (partials fill coverage) and
    any ``r < 0`` is a genuine encoding error (log + skip; only -0.6/-0.7
    observed in probe 001). A ``round(r, 2)`` scrubs float noise; ``r`` is
    already an egg-code tenth.
    """
    if single_stage:
        return TRACE_CONCENTRATION
    r = round(ct_eff - ((ca or 0.0) + (cb or 0.0) + (cc or 0.0)), 2)
    if r > 0.0:
        return r
    if r == 0.0:
        return TRACE_CONCENTRATION
    log.warning("SD residual %.2f < 0 after '9+' reconciliation; CD "
                "concentration set to 0 (genuine encoding error, DEC-044)", r)
    return 0.0


def attribute_polygon(*, ct: str | None = None, ca: str | None = None,
                      cb: str | None = None, cc: str | None = None,
                      cn: str | None = None, sa: str | None = None,
                      sb: str | None = None, sc: str | None = None,
                      cd: str | None = None) -> PolygonAttribution:
    """Regime-aware per-slot attribution of one polygon's raw SIGRID-3 codes.

    Concentrations parse through CONCENTRATION_FRACTION, thicknesses through
    STAGE_OF_DEVELOPMENT_THICKNESS. Regime split (DEC-029, probe 004): the
    **single-stage** regime (SA present, CA absent) attributes the whole CT to
    slot A; **multi-stage** uses the named partials CA/CB/CC. CN carries the SO
    trace; CD the SD residual concentration. Missing partials contribute 0; a
    polygon with CT but no stage codes (``orphan_ct``, DEC-026) yields ``ct``
    populated with every slot 0 — i.e. 0 volume, counted only in the total.
    Non-canonical blind spots (empty/other/stage_only, probe 004) need no branch
    here: they fall out as 0-volume; counting them is a caller/probe concern.
    """
    ct_f = parse_concentration(ct) or 0.0
    ca_f = parse_concentration(ca)
    cb_f = parse_concentration(cb)
    cc_f = parse_concentration(cc)

    # CT_eff: '9+' (code 91) reconciles to full coverage 1.0 for the SD residual
    # only (DEC-044); slot A keeps parse('91')=0.97 (DEC-015).
    ct_eff = 1.0 if ct == "91" else ct_f

    conc: dict[str, float] = {s: 0.0 for s in SLOTS}
    thk: dict[str, float | None] = {s: None for s in SLOTS}

    single_stage = _present(sa) and not _present(ca)

    # Slot O — SO trace (CN is the SO stage code).
    if _present(cn):
        conc["O"] = TRACE_CONCENTRATION
        thk["O"] = parse_stage_thickness(cn)

    # Slot A — single-stage attributes CT here; multi-stage uses the CA partial.
    if _present(sa):
        thk["A"] = parse_stage_thickness(sa)
    conc["A"] = ct_f if single_stage else (ca_f or 0.0)

    # Slots B, C — named partials (concentration independent of stage presence).
    if _present(sb):
        thk["B"] = parse_stage_thickness(sb)
    conc["B"] = cb_f or 0.0
    if _present(sc):
        thk["C"] = parse_stage_thickness(sc)
    conc["C"] = cc_f or 0.0

    # Slot D — SD remaining class (CD is the SD stage code).
    if _present(cd):
        thk["D"] = parse_stage_thickness(cd)
        conc["D"] = _sd_concentration(ct_eff=ct_eff, ca=ca_f, cb=cb_f, cc=cc_f,
                                      single_stage=single_stage)

    return PolygonAttribution(ct=ct_f, conc=conc, thk=thk)
