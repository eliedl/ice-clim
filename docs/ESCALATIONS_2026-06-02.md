# Reading-Log Escalations — parked 2026-06-02

**Temporary scratch.** Action items surfaced from the `[CIS Archive No.1 2006]` reading
that need work beyond the reading log. **Scheduled to be handled Thursday 2026-06-04.**
Delete this file once all items are resolved/promoted (to DECISIONS.md, a probe, etc.).

Source notes live in [READING_LOG.md](READING_LOG.md) (bullets marked `[escalation — parked]`).

---

## 1. "9+" total concentration = 97% (not 100%)

`[CIS Archive No.1 2006]`: the Digital Archive's numerical attributes encode "9+" total
concentration as **9.7/10 (97%)**, differing from the sum of partial concentrations
(10/10 = 100%). Applies to all regions and all years.

**Action:** verify `parse_concentration` handles "9+" correctly and does not conflate it
with 100%. Check `climatology/services/units_conversion_maps.py`. Likely a **DECISIONS.md**
entry once behaviour is confirmed/decided.

## 2. Chart-extent consistency (bbox)

`[CIS Archive No.1 2006]`: chart extents change across the dataset; a consistent analysis
area must be enforced or values are affected.

**Resolution (Élie):** use a bbox that intersects all chart bounding boxes present in the
archive. **No problem in the coastal setup** — the coastal bbox is far smaller than the
SGRDA GULF and WIS28 global extents. But a **basin-wide / whole-Gulf climatology must
adopt the more restrictive bbox (WIS28)** for computation. Note for later; no action now
within coastal scope.

## 3. 1982 ratio→egg trace change (SGRDREC volume)

`[CIS Archive No.1 2006]`: trace-ice counts drop in 1982 when the ratio code (multiple
traces/polygon) was replaced by the egg code (only 1 thick + 1 thin trace). Recollection:
all charts carry `E_` fields 1968–2019.

**Resolution (Élie):** simple normalization = compute volume on `E_` fields. `R_` fields
could give a better pre-1983 volume estimate but are **lower priority**. Needs a probe to
confirm `E_`-field availability across the SGRDREC range.
