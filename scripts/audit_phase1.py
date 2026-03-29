"""
Phase 1 Data Audit Script for CIS SIGRID3 Archive
Tasks 1.4, 1.5, 1.6
"""

import os
import sys
import struct
import datetime
from pathlib import Path
from collections import defaultdict, Counter

ARCHIVE = Path("C:/Users/dumas/Documents/archive/ice-raw-data-MPO")

# ─────────────────────────────────────────────────────────────────────────────
# DBF reader (no external deps required)
# ─────────────────────────────────────────────────────────────────────────────

def read_dbf(path):
    """
    Minimal DBF reader. Returns (fields, records) where
    fields = list of (name, type, length, decimal)
    records = list of dicts
    """
    with open(path, 'rb') as f:
        # Header
        header = f.read(32)
        version = header[0]
        num_records = struct.unpack_from('<I', header, 4)[0]
        header_size = struct.unpack_from('<H', header, 8)[0]
        record_size = struct.unpack_from('<H', header, 10)[0]

        # Field descriptors
        fields = []
        while True:
            fd = f.read(32)
            if fd[0] == 0x0D:
                break
            name = fd[0:11].split(b'\x00')[0].decode('latin-1')
            ftype = chr(fd[11])
            length = fd[16]
            decimal = fd[17]
            fields.append((name, ftype, length, decimal))

        # Data
        f.seek(header_size)
        records = []
        for _ in range(num_records):
            raw = f.read(record_size)
            if not raw or raw[0] == ord('*'):  # deleted record
                continue
            rec = {}
            pos = 1  # skip deletion flag
            for name, ftype, length, decimal in fields:
                val = raw[pos:pos+length].decode('latin-1').strip()
                rec[name] = val
                pos += length
            records.append(rec)
    return fields, records


# ─────────────────────────────────────────────────────────────────────────────
# TASK 1.4 — Archive structure
# ─────────────────────────────────────────────────────────────────────────────

def task_1_4():
    print("\n" + "="*70)
    print("TASK 1.4 — Archive Structure Inspection")
    print("="*70)

    folders = sorted([d.name for d in ARCHIVE.iterdir() if d.is_dir()])
    total = len(folders)
    print(f"\nTotal dated folders: {total}")
    print(f"Date range: {folders[0]} — {folders[-1]}")

    # Count by decade
    decade_counts = defaultdict(int)
    for f in folders:
        decade = f[:3] + '0'
        decade_counts[decade] += 1
    print("\nFolders per decade:")
    for d in sorted(decade_counts):
        print(f"  {d}s: {decade_counts[d]}")

    # Sample from each decade
    decades = ['196', '197', '198', '199', '200', '201', '202']
    samples = {}
    for d in decades:
        matching = [f for f in folders if f.startswith(d)]
        if matching:
            # pick first, middle, last
            idxs = [0, len(matching)//2, -1]
            samples[d+'0s'] = [matching[i] for i in idxs]

    print("\nDecade samples (first / mid / last):")
    for decade, samps in samples.items():
        print(f"  {decade}: {samps}")

    # File types and naming patterns
    print("\nFile contents per folder (sampled):")
    file_type_counts = Counter()
    naming_patterns = Counter()
    has_daily = 0
    has_weekly = 0
    both = 0

    sample_folders = []
    for d in decades:
        matching = [f for f in folders if f.startswith(d)]
        if matching:
            sample_folders.extend(matching[::max(1, len(matching)//3)][:3])

    for fname in sample_folders:
        fpath = ARCHIVE / fname
        files = list(fpath.iterdir())
        exts = Counter(f.suffix for f in files)
        for ext, cnt in exts.items():
            file_type_counts[ext] += cnt
        stems = set(f.stem for f in files)
        has_d = any('GEC_D_' in s for s in stems)
        has_h = any('GEC_H_' in s for s in stems)
        for f in files:
            name = f.name
            if name.startswith('GEC_H_'):
                naming_patterns['GEC_H_YYYYMMDD.*'] += 1
            elif name.startswith('GEC_D_'):
                naming_patterns['GEC_D_YYYYMMDD.*'] += 1
            else:
                naming_patterns[f'OTHER:{name}'] += 1
        if has_d and has_h:
            both += 1
        elif has_d:
            has_daily += 1
        elif has_h:
            has_weekly += 1

    # Full sweep for daily vs weekly
    daily_only = 0
    weekly_only = 0
    both_types = 0
    for fname in folders:
        fpath = ARCHIVE / fname
        files = [f.name for f in fpath.iterdir()]
        has_d = any(f.startswith('GEC_D_') for f in files)
        has_h = any(f.startswith('GEC_H_') for f in files)
        if has_d and has_h:
            both_types += 1
        elif has_d:
            daily_only += 1
        elif has_h:
            weekly_only += 1

    print(f"\nChart type breakdown (all {total} folders):")
    print(f"  Weekly only (GEC_H_*): {weekly_only}")
    print(f"  Daily only  (GEC_D_*): {daily_only}")
    print(f"  Both types:            {both_types}")

    print("\nFile extensions observed (sampled):")
    for ext, cnt in sorted(file_type_counts.items()):
        print(f"  {ext}: {cnt}")

    print("\nNaming patterns (sampled):")
    for pat, cnt in sorted(naming_patterns.items()):
        print(f"  {pat}: {cnt}")

    # Check for .prj presence (some daily folders missing it)
    no_prj_h = 0
    no_prj_d = 0
    prj_sample = []
    for fname in folders[:200]:
        fpath = ARCHIVE / fname
        files = [f.name for f in fpath.iterdir()]
        has_h_shp = any(f.startswith('GEC_H_') and f.endswith('.shp') for f in files)
        has_h_prj = any(f.startswith('GEC_H_') and f.endswith('.prj') for f in files)
        has_d_shp = any(f.startswith('GEC_D_') and f.endswith('.shp') for f in files)
        has_d_prj = any(f.startswith('GEC_D_') and f.endswith('.prj') for f in files)
        if has_h_shp and not has_h_prj:
            no_prj_h += 1
        if has_d_shp and not has_d_prj:
            no_prj_d += 1

    print(f"\nMissing .prj files (first 200 folders):")
    print(f"  GEC_H_* without .prj: {no_prj_h}")
    print(f"  GEC_D_* without .prj: {no_prj_d}")

    # Schema sampling: read DBF from 5 different decades
    print("\n" + "-"*50)
    print("Schema sampling — DBF field inventory")
    print("-"*50)

    schema_samples = []
    for d in decades:
        matching = [f for f in folders if f.startswith(d)]
        if matching:
            # Pick the ~middle one, prefer weekly
            for fname in matching[len(matching)//2:len(matching)//2+10]:
                fpath = ARCHIVE / fname
                shps = [f for f in fpath.iterdir() if f.name.startswith('GEC_H_') and f.suffix == '.dbf']
                if shps:
                    schema_samples.append((d+'0s', fname, shps[0]))
                    break

    for decade, folder, dbf_path in schema_samples:
        try:
            fields, records = read_dbf(dbf_path)
            print(f"\n[{decade}] {folder}/{dbf_path.name}")
            print(f"  Records: {len(records)}")
            print(f"  Fields ({len(fields)}):")
            for name, ftype, length, decimal in fields:
                print(f"    {name:<20} type={ftype} len={length} dec={decimal}")
        except Exception as e:
            print(f"  ERROR reading {dbf_path}: {e}")

    return schema_samples


# ─────────────────────────────────────────────────────────────────────────────
# TASK 1.5 — Edge Case Analysis
# ─────────────────────────────────────────────────────────────────────────────

SIGRID3_CONCENTRATION = {'0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
                          'X', '/', '-', ''}
SIGRID3_STAGE = {'0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                  '1.', '4.', 'X', '/', '-', ''}
SIGRID3_FORM  = {'0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                  'X', '/', '-', ''}

EGG_FIELDS = {
    'conc': ['E_CT', 'E_CA', 'E_CB', 'E_CC'],
    'stage': ['E_SA', 'E_SB', 'E_SC'],
    'form': ['E_FA', 'E_FB', 'E_FC'],
}

def task_1_5(schema_samples):
    print("\n" + "="*70)
    print("TASK 1.5 — Edge Case Analysis")
    print("="*70)

    # Collect a broader sample: one folder per year, prefer weekly
    folders = sorted([d.name for d in ARCHIVE.iterdir() if d.is_dir()])

    # Group by year
    by_year = defaultdict(list)
    for f in folders:
        by_year[f[:4]].append(f)

    all_values = defaultdict(Counter)   # field -> Counter of values
    conc_violation_count = 0
    conc_check_total = 0
    geom_invalid = 0
    geom_total = 0
    sample_records_total = 0
    null_counts = defaultdict(int)
    sentinel_counts = defaultdict(lambda: defaultdict(int))
    out_of_spec = defaultdict(set)
    years_sampled = []

    for year in sorted(by_year.keys()):
        # pick one weekly folder per year
        for fname in by_year[year]:
            fpath = ARCHIVE / fname
            dbfs = [f for f in fpath.iterdir() if f.name.startswith('GEC_H_') and f.suffix == '.dbf']
            if not dbfs:
                continue
            dbf_path = dbfs[0]
            try:
                fields, records = read_dbf(dbf_path)
                field_names = [f[0] for f in fields]
                years_sampled.append(year)
                sample_records_total += len(records)

                for rec in records:
                    # Collect unique values per egg field
                    for field_group, field_list in EGG_FIELDS.items():
                        for fn in field_list:
                            if fn in rec:
                                v = rec[fn].strip() if rec[fn] else ''
                                all_values[fn][v] += 1
                                if v == '' or v is None:
                                    null_counts[fn] += 1
                                if v in ('X', '/', '-'):
                                    sentinel_counts[fn][v] += 1
                                # Check spec compliance
                                if field_group == 'conc' and v not in SIGRID3_CONCENTRATION:
                                    out_of_spec[fn].add(v)
                                elif field_group == 'stage' and v not in SIGRID3_STAGE:
                                    out_of_spec[fn].add(v)
                                elif field_group == 'form' and v not in SIGRID3_FORM:
                                    out_of_spec[fn].add(v)

                    # Partial concentration sum check: E_CA + E_CB + E_CC <= E_CT
                    if all(f in rec for f in ['E_CT', 'E_CA', 'E_CB', 'E_CC']):
                        conc_check_total += 1
                        try:
                            ct = int(rec['E_CT']) if rec['E_CT'].strip().isdigit() else None
                            ca = int(rec['E_CA']) if rec['E_CA'].strip().isdigit() else None
                            cb = int(rec['E_CB']) if rec['E_CB'].strip().isdigit() else None
                            cc = int(rec['E_CC']) if rec['E_CC'].strip().isdigit() else None
                            if ct is not None and ca is not None:
                                total_partial = ca + (cb or 0) + (cc or 0)
                                if total_partial > ct:
                                    conc_violation_count += 1
                        except (ValueError, AttributeError):
                            pass

            except Exception as e:
                print(f"  WARN: could not read {dbf_path}: {e}")
            break  # one folder per year

    print(f"\nYears sampled: {len(years_sampled)} ({years_sampled[0]}–{years_sampled[-1]})")
    print(f"Total records inspected: {sample_records_total:,}")

    print("\n--- Unique values per Egg Code field ---")
    all_egg_fields = EGG_FIELDS['conc'] + EGG_FIELDS['stage'] + EGG_FIELDS['form']
    for fn in all_egg_fields:
        if fn in all_values:
            vals = dict(all_values[fn].most_common(30))
            print(f"\n  {fn}:")
            print(f"    Unique values ({len(all_values[fn])}): {sorted(all_values[fn].keys())}")
            print(f"    Top values: {dict(list(all_values[fn].most_common(10)))}")
            if fn in null_counts:
                print(f"    Nulls/empty: {null_counts[fn]:,}")
            if fn in sentinel_counts:
                print(f"    Sentinels: {dict(sentinel_counts[fn])}")
            if fn in out_of_spec:
                print(f"    OUT-OF-SPEC values: {out_of_spec[fn]}")
        else:
            print(f"\n  {fn}: NOT FOUND in sampled data")

    print(f"\n--- Partial concentration sum check ---")
    print(f"  Records with all 4 conc fields numeric: {conc_check_total:,}")
    print(f"  Violations (E_CA+E_CB+E_CC > E_CT):     {conc_violation_count:,}")
    if conc_check_total > 0:
        pct = 100 * conc_violation_count / conc_check_total
        print(f"  Violation rate: {pct:.2f}%")

    return all_values, sentinel_counts, out_of_spec, null_counts


# ─────────────────────────────────────────────────────────────────────────────
# TASK 1.6 — Temporal Coverage Analysis
# ─────────────────────────────────────────────────────────────────────────────

def task_1_6():
    print("\n" + "="*70)
    print("TASK 1.6 — Temporal Coverage Analysis")
    print("="*70)

    folders = sorted([d.name for d in ARCHIVE.iterdir() if d.is_dir()])

    # Parse all dates
    dates_weekly = []
    dates_daily = []
    dates_by_ym_weekly = defaultdict(int)   # (year, month) -> count
    dates_by_ym_daily  = defaultdict(int)

    for fname in folders:
        fpath = ARCHIVE / fname
        files = [f.name for f in fpath.iterdir()]
        has_h = any(f.startswith('GEC_H_') for f in files)
        has_d = any(f.startswith('GEC_D_') for f in files)
        try:
            dt = datetime.date(int(fname[:4]), int(fname[4:6]), int(fname[6:8]))
        except ValueError:
            continue
        ym = (dt.year, dt.month)
        if has_h:
            dates_weekly.append(dt)
            dates_by_ym_weekly[ym] += 1
        if has_d:
            dates_daily.append(dt)
            dates_by_ym_daily[ym] += 1

    all_dates = sorted(set(dates_weekly + dates_daily))

    print(f"\nTotal unique observation dates: {len(all_dates)}")
    print(f"Weekly charts: {len(dates_weekly)} dates")
    print(f"Daily charts:  {len(dates_daily)} dates")
    print(f"  Daily start: {min(dates_daily) if dates_daily else 'N/A'}")
    print(f"  Daily end:   {max(dates_daily) if dates_daily else 'N/A'}")

    # Gaps analysis — find gaps >= 14 days in weekly chart dates
    print("\n--- Gaps >= 14 days in weekly chart sequence ---")
    gaps = []
    prev = None
    for dt in sorted(dates_weekly):
        if prev:
            delta = (dt - prev).days
            if delta >= 14:
                gaps.append((prev, dt, delta))
        prev = dt
    gaps.sort(key=lambda x: -x[2])
    print(f"  Total gaps >= 14 days: {len(gaps)}")
    print(f"  Largest gaps (top 20):")
    for g in gaps[:20]:
        print(f"    {g[0]} → {g[1]}: {g[2]} days")

    # Year × Month table
    if not dates_by_ym_weekly:
        print("\nNo weekly data found.")
        return

    years = sorted(set(y for y, m in dates_by_ym_weekly))
    months = list(range(1, 13))

    print("\n--- Year × Month count of WEEKLY (GEC_H_*) charts ---")
    header = "Year  " + " ".join(f"{m:>3}" for m in months) + "  Total"
    print(header)
    print("-" * len(header))

    low_coverage_years = []
    for yr in years:
        row_vals = [dates_by_ym_weekly.get((yr, m), 0) for m in months]
        total = sum(row_vals)
        row = f"{yr}  " + " ".join(f"{v:>3}" if v > 0 else "  ." for v in row_vals) + f"  {total:>4}"
        print(row)
        if total < 20:
            low_coverage_years.append((yr, total))

    print(f"\nYears with < 20 weekly charts: {low_coverage_years}")

    # Daily coverage table
    if dates_by_ym_daily:
        years_d = sorted(set(y for y, m in dates_by_ym_daily))
        print("\n--- Year × Month count of DAILY (GEC_D_*) charts ---")
        header_d = "Year  " + " ".join(f"{m:>3}" for m in months) + "  Total"
        print(header_d)
        print("-" * len(header_d))
        for yr in years_d:
            row_vals = [dates_by_ym_daily.get((yr, m), 0) for m in months]
            total = sum(row_vals)
            row = f"{yr}  " + " ".join(f"{v:>3}" if v > 0 else "  ." for v in row_vals) + f"  {total:>4}"
            print(row)

    # Reference period assessment
    print("\n--- Coverage by candidate reference periods ---")
    for period_name, start_y, end_y in [
        ("1961–1990", 1961, 1990),
        ("1981–2010", 1981, 2010),
        ("1991–2020", 1991, 2020),
    ]:
        period_years = [yr for yr in years if start_y <= yr <= end_y]
        total_charts = sum(
            dates_by_ym_weekly.get((yr, m), 0)
            for yr in period_years for m in months
        )
        complete_years = [yr for yr in period_years if
                          sum(dates_by_ym_weekly.get((yr, m), 0) for m in months) >= 20]
        print(f"\n  {period_name}:")
        print(f"    Years with data: {len(period_years)}/{end_y - start_y + 1}")
        print(f"    Total weekly charts: {total_charts}")
        print(f"    Years with >=20 weekly charts: {len(complete_years)}")
        if len(period_years) > 0:
            missing = set(range(start_y, end_y+1)) - set(period_years)
            if missing:
                print(f"    Years with NO data: {sorted(missing)}")

    return dates_by_ym_weekly, dates_by_ym_daily, gaps


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("CIS SIGRID3 Archive Audit — Phase 1")
    print(f"Archive: {ARCHIVE}")
    print(f"Run date: {datetime.date.today()}")

    schema_samples = task_1_4()
    edge_data = task_1_5(schema_samples)
    temporal_data = task_1_6()

    print("\n\nAudit complete.")
