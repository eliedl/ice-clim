"""SIGRID-3 unit conversion maps for CIS sea-ice data."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from climatology.utils._types import ConvertedPolygons, RawPolygons

log = logging.getLogger(__name__)


# --- Conversion maps

# Uniform CIS trace concentration (DEC-044). Equals map('92') - map('91').
TRACE_CONCENTRATION: float = 0.03

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
MISSING_CODES: frozenset[str] = frozenset({"-9", "9-"})
_TYPO_SUBSTITUTIONS: dict[str, str] = {"8": "80", "9": "90"}


STAGE_OF_DEVELOPMENT_THICKNESS: dict[str, float | None] = {
    "81": 0.050,   # New Ice                (<10 cm)
    "84": 0.125,   # Grey Ice               (10-15 cm)
    "85": 0.225,   # Grey-White Ice         (15-30 cm)
    "86": 1.150,   # First Year Ice (broad) (30-200 cm)
    "87": 0.500,   # Thin First Year Ice    (30-70 cm)
    "91": 0.950,   # Medium First Year Ice  (70-120 cm)
    "93": 1.600,   # Thick First Year Ice   (>=120 cm; midpoint 120-200)
    "95": 1.600,   # Old Ice                — code-93 family (DEC-043)
    "96": 1.600,   # Second Year Ice        — code-93 family (DEC-043)
    "97": 1.600,   # Multi-Year Ice         — code-93 family (DEC-043)
    "98": None,    # Glacier Ice            — excluded (DEC-043)
    "99": None,    # Undetermined / Unknown — excluded (DEC-043)
}
INVALID_STAGE_CODES: frozenset[str] = frozenset({"7C", "9C", "5-", "6-", "10", "50"})


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
INVALID_FORM_CODES: frozenset[str] = frozenset({"2C", "5C", "9C"})

# --- Presence predicate
def _is_missing(code: str | float | None) -> bool:
    """True for absent codes: None, NaN (DB NULL surfaced by pandas), empty, or a sentinel."""
    return code is None or isinstance(code, float) or code == "" or code in MISSING_CODES

# --- Parsers
def parse_concentration(code: str | float | None) -> float | None:
    """Concentration code -> fraction [0, 1]; None if missing, KeyError on novel codes."""
    if _is_missing(code):
        return None
    canonical = _TYPO_SUBSTITUTIONS.get(code, code)
    try:
        return CONCENTRATION_FRACTION[canonical]
    except KeyError as e:
        raise KeyError(f"Unrecognised SIGRID-3 concentration code: {code!r}") from e

def parse_stage_thickness(code: str | float | None) -> float | None:
    """Stage-of-development code -> midpoint thickness (m); None if missing/invalid/no-thickness, KeyError on novel codes."""
    if _is_missing(code) or code in INVALID_STAGE_CODES:
        return None
    try:
        return STAGE_OF_DEVELOPMENT_THICKNESS[code]
    except KeyError as e:
        raise KeyError(f"Unrecognised SIGRID-3 stage-of-development code: {code!r}") from e

def parse_form_size(code: str | float | None) -> float | None:
    """Form-of-ice code -> representative floe diameter (m); None if missing/invalid/no-floe-class, KeyError on novel codes."""
    if _is_missing(code) or code in INVALID_FORM_CODES:
        return None
    try:
        return FORM_SIZES[code]
    except KeyError as e:
        raise KeyError(f"Unrecognised SIGRID-3 form-of-ice code: {code!r}") from e


@dataclass(frozen=True)
class ConversionStrategy:
    """Strategy: prepare a metric's raw <field>_code columns into the value column(s) its kernel consumes.

    ``value_cols`` declares which prepared columns the reduction burns, in the
    same order as the kernel's per-variable thresholds.
    """

    prepare: Callable[[RawPolygons], ConvertedPolygons]
    value_cols: tuple[str, ...] = ("ct",)


def _present_col(s: pd.Series) -> np.ndarray:
    """Vectorized _is_missing inverse: True where a code column carries information."""
    return (s.notna() & (s != "") & ~s.isin(MISSING_CODES)).to_numpy()


def egg_code_units(df: RawPolygons) -> ConvertedPolygons:
    """Add ``ct``, ``mean_thk`` and ``volume_per_area`` (CT × Σ(conc·thk)/Σ(conc)) by vectorized regime-aware egg-code attribution.

    ``ct`` keeps NaN for missing CT codes (the probe-004 ``empty``/``stage_only``
    rows) so threshold kernels see those cells as unobserved, not ice-free;
    the zero-filled ``ct0`` stays internal to the volume product, where
    "missing contributes 0" is the census skip policy.
    """
    conc_of = lambda col: df[col].replace(_TYPO_SUBSTITUTIONS).map(CONCENTRATION_FRACTION).to_numpy()
    thk_of = lambda col: df[col].map(STAGE_OF_DEVELOPMENT_THICKNESS).to_numpy(dtype=float)

    ct0 = np.nan_to_num(df["ct_code"].map(CONCENTRATION_FRACTION).to_numpy())
    ca0, cb0, cc0 = (np.nan_to_num(conc_of(c)) for c in ("ca_code", "cb_code", "cc_code"))

    single = _present_col(df["sa_code"]) & ~_present_col(df["ca_code"])
    cd_pres = _present_col(df["cd_code"])

    ct_eff = np.where(df["ct_code"].eq("91").to_numpy(), 1.0, ct0)
    r = np.round(ct_eff - (ca0 + cb0 + cc0), 2)

    conc_A = np.where(single, ct0, ca0)
    conc_O = np.where(_present_col(df["cn_code"]), TRACE_CONCENTRATION, 0.0)
    conc_D = np.where(cd_pres,
                      np.select([single, r > 0.0], [TRACE_CONCENTRATION, r], TRACE_CONCENTRATION),
                      0.0)

    n_neg = int((cd_pres & ~single & (r < 0.0)).sum())
    if n_neg:
        log.warning("%d SD residual(s) < 0 after '9+' reconciliation; CD attributed "
                    "trace concentration (genuine encoding error, DEC-044)", n_neg)

    conc = np.column_stack([conc_O, conc_A, cb0, cc0, conc_D])
    thk = np.column_stack([thk_of(c) for c in ("cn_code", "sa_code", "sb_code", "sc_code", "cd_code")])
    weight = np.where(np.isnan(thk), 0.0, conc)
    denom = weight.sum(axis=1)
    mean_thk = np.divide(np.nansum(weight * np.nan_to_num(thk), axis=1), denom,
                         out=np.zeros_like(denom), where=denom > 0.0)
    
    return df.assign(ct=df["ct_code"].map(CONCENTRATION_FRACTION),
                     mean_thk=mean_thk,
                     volume_per_area=ct0 * mean_thk)

# --- Conversions
CT_CONVERSION            = ConversionStrategy(lambda df: df.assign(ct=df["ct_code"].map(CONCENTRATION_FRACTION)))
LANDFAST_CONVERSION      = ConversionStrategy(lambda df: df.assign(ct=(df["fa_code"] == "08").astype(float)))
DEVELOPED_ICE_CONVERSION = ConversionStrategy(egg_code_units, value_cols=("ct", "mean_thk"))
VOLUME_CONVERSION        = ConversionStrategy(egg_code_units, value_cols=("volume_per_area",))

