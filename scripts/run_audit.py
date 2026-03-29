"""
Phase 1 Data Audit — outputs results to a text file
"""
import os, sys, struct, datetime, json
from pathlib import Path
from collections import defaultdict, Counter

ARCHIVE = Path("C:/Users/dumas/Documents/archive/ice-raw-data-MPO")
OUT = Path("C:/Users/dumas/Documents/perso/ice-clim/scripts/audit_output.json")

def read_dbf_header(path):
    """Return (num_records, fields_list) from DBF header only."""
    with open(path, 'rb') as f:
        header = f.read(32)
        num_records = struct.unpack_from('<I', header, 4)[0]
        header_size = struct.unpack_from('<H', header, 8)[0]
        record_size = struct.unpack_from('<H', header, 10)[0]
        fields = []
        while True:
            fd = f.read(32)
            if not fd or fd[0] == 0x0D:
                break
            if len(fd) < 18:
                break
            name = fd[0:11].split(b'\x00')[0].decode('latin-1', errors='replace')
            ftype = chr(fd[11]) if fd[11] >= 32 else '?'
            length = fd[16]
            decimal = fd[17]
            fields.append({'name': name, 'type': ftype, 'len': length, 'dec': decimal})
    return num_records, fields, record_size

def read_dbf_full(path):
    """Return (fields, records). Records are dicts of field->string value."""
    with open(path, 'rb') as f:
        header = f.read(32)
        num_records = struct.unpack_from('<I', header, 4)[0]
        header_size = struct.unpack_from('<H', header, 8)[0]
        record_size = struct.unpack_from('<H', header, 10)[0]
        fields = []
        while True:
            fd = f.read(32)
            if not fd or fd[0] == 0x0D:
                break
            if len(fd) < 18:
                break
            name = fd[0:11].split(b'\x00')[0].decode('latin-1', errors='replace')
            ftype = chr(fd[11]) if fd[11] >= 32 else '?'
            length = fd[16]
            decimal = fd[17]
            fields.append({'name': name, 'type': ftype, 'len': length, 'dec': decimal})
        f.seek(header_size)
        records = []
        for _ in range(num_records):
            raw = f.read(record_size)
            if not raw:
                break
            if raw[0] == ord('*'):
                continue
            rec = {}
            pos = 1
            for fld in fields:
                val = raw[pos:pos+fld['len']].decode('latin-1', errors='replace').strip()
                rec[fld['name']] = val
                pos += fld['len']
            records.append(rec)
    return fields, records

results = {}

# ── TASK 1.4: Archive structure ──────────────────────────────────────────────
folders = sorted([d.name for d in ARCHIVE.iterdir() if d.is_dir()])
results['total_folders'] = len(folders)
results['date_range'] = [folders[0], folders[-1]]

# Count by decade
decade_counts = defaultdict(int)
for f in folders:
    decade_counts[f[:3]+'0'] += 1
results['decade_counts'] = dict(decade_counts)

# Chart type breakdown — full sweep
daily_only = weekly_only = both_types = 0
folder_types = {}
for fname in folders:
    fpath = ARCHIVE / fname
    try:
        files = [f.name for f in fpath.iterdir()]
    except:
        continue
    has_d = any(f.startswith('GEC_D_') for f in files)
    has_h = any(f.startswith('GEC_H_') for f in files)
    has_new = any(f.startswith('cis_SGRDAWIS28') for f in files)
    if has_new:
        folder_types[fname] = 'new_format'
    elif has_d and has_h:
        both_types += 1
        folder_types[fname] = 'both'
    elif has_d:
        daily_only += 1
        folder_types[fname] = 'daily'
    elif has_h:
        weekly_only += 1
        folder_types[fname] = 'weekly'
    else:
        folder_types[fname] = 'unknown'

results['chart_types'] = {
    'weekly_only': weekly_only,
    'daily_only': daily_only,
    'both': both_types,
    'new_format': sum(1 for v in folder_types.values() if v == 'new_format'),
    'unknown': sum(1 for v in folder_types.values() if v == 'unknown'),
}

# File extensions — sampled
ext_counter = Counter()
for fname in list(folders)[::100]:
    fpath = ARCHIVE / fname
    try:
        for f in fpath.iterdir():
            ext_counter[f.suffix.lower()] += 1
    except:
        pass
results['file_extensions_sampled'] = dict(ext_counter)

# Transition to daily — find first daily folder
first_daily = next((f for f in folders if folder_types.get(f) in ('daily', 'both')), None)
results['first_daily_folder'] = first_daily

# New format transition
first_new = next((f for f in folders if folder_types.get(f) == 'new_format'), None)
results['first_new_format_folder'] = first_new

# Schema sampling: read headers from 1 weekly shapefile per decade
schema_by_decade = {}
for decade_prefix, decade_label in [('196','1960s'),('197','1970s'),('198','1980s'),
                                      ('199','1990s'),('200','2000s'),('201','2010s'),('202','2020s')]:
    matching = [f for f in folders if f.startswith(decade_prefix)]
    for fname in matching[len(matching)//2:len(matching)//2+20]:
        fpath = ARCHIVE / fname
        try:
            dbfs = [f for f in fpath.iterdir() if f.name.startswith('GEC_H_') and f.suffix == '.dbf']
        except:
            continue
        if dbfs:
            try:
                n, flds, recsz = read_dbf_header(dbfs[0])
                schema_by_decade[decade_label] = {
                    'folder': fname,
                    'file': dbfs[0].name,
                    'num_records': n,
                    'record_size': recsz,
                    'fields': flds
                }
                break
            except Exception as e:
                schema_by_decade[decade_label] = {'error': str(e), 'folder': fname}
results['schema_by_decade'] = schema_by_decade

# Also read the new format
new_folders = [f for f in folders if folder_types.get(f) == 'new_format']
if new_folders:
    fname = new_folders[0]
    fpath = ARCHIVE / fname
    try:
        dbfs = [f for f in fpath.iterdir() if f.suffix == '.dbf']
        if dbfs:
            n, flds, recsz = read_dbf_header(dbfs[0])
            results['schema_new_format'] = {
                'folder': fname,
                'file': dbfs[0].name,
                'num_records': n,
                'record_size': recsz,
                'fields': flds
            }
    except Exception as e:
        results['schema_new_format'] = {'error': str(e)}

# ── TASK 1.5: Edge case analysis ─────────────────────────────────────────────
EGG_FIELDS = ['E_CT','E_CA','E_CB','E_CC','E_SA','E_SB','E_SC','E_FA','E_FB','E_FC']
field_values = defaultdict(Counter)
conc_violations = 0
conc_total = 0
total_records = 0
years_sampled = []

# one weekly per year
by_year = defaultdict(list)
for f in folders:
    by_year[f[:4]].append(f)

for year in sorted(by_year.keys()):
    for fname in by_year[year]:
        if folder_types.get(fname) not in ('weekly', 'both'):
            continue
        fpath = ARCHIVE / fname
        try:
            dbfs = [f for f in fpath.iterdir() if f.name.startswith('GEC_H_') and f.suffix == '.dbf']
        except:
            continue
        if not dbfs:
            continue
        try:
            flds, recs = read_dbf_full(dbfs[0])
            years_sampled.append(year)
            total_records += len(recs)
            for rec in recs:
                for fn in EGG_FIELDS:
                    if fn in rec:
                        field_values[fn][rec[fn]] += 1
                # conc sum check
                try:
                    ct_s = rec.get('E_CT','').strip()
                    ca_s = rec.get('E_CA','').strip()
                    cb_s = rec.get('E_CB','').strip()
                    cc_s = rec.get('E_CC','').strip()
                    if ct_s.lstrip('-').isdigit() and ca_s.lstrip('-').isdigit():
                        conc_total += 1
                        ct = int(ct_s); ca = int(ca_s)
                        cb = int(cb_s) if cb_s.lstrip('-').isdigit() else 0
                        cc = int(cc_s) if cc_s.lstrip('-').isdigit() else 0
                        if ca + cb + cc > ct:
                            conc_violations += 1
                except:
                    pass
        except Exception as e:
            pass
        break  # one per year

results['edge_cases'] = {
    'years_sampled': years_sampled,
    'total_records': total_records,
    'field_values': {k: dict(v.most_common(50)) for k, v in field_values.items()},
    'conc_violations': conc_violations,
    'conc_total': conc_total,
}

# ── TASK 1.6: Temporal coverage ───────────────────────────────────────────────
dates_by_ym_weekly = defaultdict(int)
dates_by_ym_daily = defaultdict(int)
dates_by_ym_new = defaultdict(int)
weekly_dates = []
daily_dates = []

for fname in folders:
    try:
        dt = datetime.date(int(fname[:4]), int(fname[4:6]), int(fname[6:8]))
    except ValueError:
        continue
    ft = folder_types.get(fname, 'unknown')
    ym = (dt.year, dt.month)
    if ft in ('weekly', 'both'):
        dates_by_ym_weekly[ym] += 1
        weekly_dates.append(dt)
    if ft in ('daily', 'both'):
        dates_by_ym_daily[ym] += 1
        daily_dates.append(dt)
    if ft == 'new_format':
        dates_by_ym_new[ym] += 1

# Gaps in weekly sequence
gaps = []
prev = None
for dt in sorted(weekly_dates):
    if prev:
        delta = (dt - prev).days
        if delta >= 14:
            gaps.append({'from': str(prev), 'to': str(dt), 'days': delta})
    prev = dt
gaps_sorted = sorted(gaps, key=lambda x: -x['days'])

results['temporal'] = {
    'weekly_dates_count': len(weekly_dates),
    'daily_dates_count': len(daily_dates),
    'new_format_dates_count': sum(dates_by_ym_new.values()),
    'first_daily': str(min(daily_dates)) if daily_dates else None,
    'last_daily': str(max(daily_dates)) if daily_dates else None,
    'gaps_ge14days': gaps_sorted[:30],
    'total_gaps': len(gaps),
    'weekly_by_ym': {f"{y}-{m:02d}": v for (y,m),v in sorted(dates_by_ym_weekly.items())},
    'daily_by_ym': {f"{y}-{m:02d}": v for (y,m),v in sorted(dates_by_ym_daily.items())},
    'new_by_ym': {f"{y}-{m:02d}": v for (y,m),v in sorted(dates_by_ym_new.items())},
}

# Reference periods
for label, sy, ey in [("1961-1990",1961,1990),("1981-2010",1981,2010),("1991-2020",1991,2020)]:
    years_with_data = set(y for y,m in dates_by_ym_weekly if sy<=y<=ey)
    total_charts = sum(v for (y,m),v in dates_by_ym_weekly.items() if sy<=y<=ey)
    years_complete = [y for y in range(sy,ey+1) if
                      sum(dates_by_ym_weekly.get((y,m),0) for m in range(1,13)) >= 20]
    results['temporal'][f'ref_period_{label}'] = {
        'years_with_data': len(years_with_data),
        'total_years': ey-sy+1,
        'total_charts': total_charts,
        'years_complete_ge20': len(years_complete),
        'missing_years': sorted(set(range(sy,ey+1)) - years_with_data),
    }

OUT.write_text(json.dumps(results, indent=2, default=str))
print(f"Done. Output: {OUT}")
