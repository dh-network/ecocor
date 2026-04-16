#!/usr/bin/env python3
"""
Rename TEI files to homogeneous format: YEAR_Surname_Title-Words.xml
Reads metadata from Literaturliste_EcoCor_Joint.csv, matches by Filename column.
Outputs a correspondence CSV and updates the source CSV with a new column.

Usage:
    python3 rename_tei.py           # dry run (preview only)
    python3 rename_tei.py --execute # perform renames and write CSVs
"""
import csv
import os
import re
import sys
import shutil

TEI_DIR = "/Users/daniilskorinkin/ACTIVITIES/DH_NETZWERK/EcoCor_and_Climate DH/EcoCor/EcoCor2026/eco-de/tei"
CSV_PATH = "/Users/daniilskorinkin/ACTIVITIES/DH_NETZWERK/EcoCor_and_Climate DH/EcoCor/EcoCor2026/TEI conversion/ecocor/corpus/aux/Literaturliste_EcoCor_Joint.csv"
CORR_CSV_PATH = "/Users/daniilskorinkin/ACTIVITIES/DH_NETZWERK/EcoCor_and_Climate DH/EcoCor/EcoCor2026/eco-de/filename_correspondence.csv"

DRY_RUN = "--execute" not in sys.argv


def transliterate(text):
    replacements = {
        'ä': 'ae', 'ö': 'oe', 'ü': 'ue',
        'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue',
        'ß': 'ss',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'à': 'a', 'â': 'a', 'á': 'a',
        'î': 'i', 'ï': 'i', 'í': 'i',
        'ô': 'o', 'ó': 'o',
        'û': 'u', 'ù': 'u', 'ú': 'u',
        'ç': 'c', 'ñ': 'n',
        '–': '-', '—': '-',
        '»': '', '«': '',
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


def get_surname(author):
    """Extract surname (with nobility particle if present) from author name."""
    # Special cases: pen names where all parts form the surname
    pen_names = {'Jean Qui Rit': 'Qui Rit', 'Jean Paul': 'Paul'}
    if author in pen_names:
        return pen_names[author]

    tokens = author.split()
    if len(tokens) == 0:
        return ''
    if len(tokens) == 1:
        return tokens[0]
    # If there's a nobility particle, surname = particle + following words
    for i in range(1, len(tokens)):
        if tokens[i].lower() in {'von', 'zu', 'van', 'de'}:
            return ' '.join(tokens[i:])
    # Otherwise just the last word
    return tokens[-1]


def clean_surname(surname):
    """Transliterate and slugify surname."""
    surname = transliterate(surname)
    surname = re.sub(r'[^\w\s-]', '', surname)
    surname = re.sub(r'\s+', '-', surname.strip())
    return surname


def clean_title(title, max_words=3):
    """Take first max_words words from title, transliterate, no punctuation, joined by hyphens."""
    title = transliterate(title)
    title = re.sub(r"[^\w\s-]", '', title)  # keep alphanumeric, spaces, hyphens
    # Strip leading/trailing hyphens from each word, filter empty
    words = [w.strip('-') for w in title.split()]
    words = [w for w in words if w]
    words = words[:max_words]
    return '-'.join(words)


def get_year(year_str):
    """Extract first 4-digit year from year field."""
    m = re.match(r'(\d{4})', year_str.strip())
    return m.group(1) if m else year_str.strip()


def normalize_key(name):
    """Normalize a filename stem for fuzzy matching."""
    name = transliterate(name)
    name = name.lower()
    name = re.sub(r'[^a-z0-9]', '', name)
    return name


# Build lookup of existing tei xml files (stem → actual filename)
tei_files = [f for f in os.listdir(TEI_DIR) if f.endswith('.xml')]
tei_by_key = {}
for f in tei_files:
    stem = f[:-4]  # strip .xml
    key = normalize_key(stem)
    tei_by_key[key] = f

# Read CSV
with open(CSV_PATH, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f, delimiter=';')
    fieldnames = reader.fieldnames
    rows = list(reader)

renames = []  # list of dicts with old_filename, new_filename, row_index
unmatched = []

for idx, row in enumerate(rows):
    filename_txt = (row.get('Filename') or '').strip()
    if not filename_txt:
        continue

    # Derive expected xml filename
    if filename_txt.endswith('.txt'):
        filename_xml = filename_txt[:-4] + '.xml'
    else:
        filename_xml = filename_txt

    # Skip already well-formatted (start with year_)
    if re.match(r'^\d{4}_', filename_xml):
        continue

    # Try to find matching file in tei/
    key = normalize_key(filename_xml[:-4])
    actual_file = tei_by_key.get(key)

    if actual_file is None:
        # Direct match attempt
        if filename_xml in tei_files:
            actual_file = filename_xml
        else:
            unmatched.append((filename_txt, filename_xml))
            continue

    # Generate new filename
    author = (row.get('Autor*in') or '').strip()
    title = (row.get('Titel') or '').strip()
    year = get_year(row.get('Jahr') or '')

    surname = get_surname(author)
    surname_clean = clean_surname(surname)
    title_clean = clean_title(title)

    new_name = f"{year}_{surname_clean}_{title_clean}.xml"

    renames.append({
        'old_filename': actual_file,
        'new_filename': new_name,
        'row_index': idx,
    })

print(f"\n{'DRY RUN — ' if DRY_RUN else ''}Processing {len(renames)} renames, {len(unmatched)} unmatched\n")

if unmatched:
    print("UNMATCHED CSV entries (no file found in tei/):")
    for txt, xml in unmatched:
        print(f"  {txt}")
    print()

# Check for duplicate new names
new_names = [r['new_filename'] for r in renames]
dupes = [n for n in set(new_names) if new_names.count(n) > 1]
if dupes:
    print("WARNING: Duplicate new filenames detected:")
    for d in dupes:
        for r in renames:
            if r['new_filename'] == d:
                print(f"  {r['old_filename']} -> {d}")
    print()

print(f"{'old_filename':<70} -> new_filename")
print("-" * 120)
for r in renames:
    print(f"  {r['old_filename']:<68} -> {r['new_filename']}")

if not DRY_RUN:
    import subprocess

    # Write correspondence CSV
    with open(CORR_CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['old_filename', 'new_filename'], delimiter=';')
        writer.writeheader()
        for r in renames:
            writer.writerow({'old_filename': r['old_filename'], 'new_filename': r['new_filename']})
    print(f"\nWrote correspondence CSV: {CORR_CSV_PATH}")

    # Update source CSV with new column 'New_Filename'
    new_col = 'New_Filename'
    if new_col not in fieldnames:
        fieldnames = list(fieldnames) + [new_col]

    # Build map from old filename to new filename
    old_to_new = {r['old_filename']: r['new_filename'] for r in renames}

    for idx, row in enumerate(rows):
        filename_txt = (row.get('Filename') or '').strip()
        filename_xml = filename_txt[:-4] + '.xml' if filename_txt.endswith('.txt') else filename_txt
        key = normalize_key(filename_xml[:-4])
        actual_file = tei_by_key.get(key) or (filename_xml if filename_xml in tei_files else None)
        if actual_file and actual_file in old_to_new:
            rows[idx][new_col] = old_to_new[actual_file]
        else:
            if new_col not in rows[idx]:
                rows[idx][new_col] = ''

    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)
    print(f"Updated source CSV with '{new_col}' column: {CSV_PATH}")

    # Perform git mv for each rename
    errors = []
    for r in renames:
        old_path = os.path.join(TEI_DIR, r['old_filename'])
        new_path = os.path.join(TEI_DIR, r['new_filename'])
        result = subprocess.run(
            ['git', 'mv', old_path, new_path],
            capture_output=True, text=True,
            cwd="/Users/daniilskorinkin/ACTIVITIES/DH_NETZWERK/EcoCor_and_Climate DH/EcoCor/EcoCor2026/eco-de"
        )
        if result.returncode != 0:
            errors.append((r['old_filename'], r['new_filename'], result.stderr.strip()))
        else:
            print(f"  git mv: {r['old_filename']} -> {r['new_filename']}")

    if errors:
        print("\nERRORS:")
        for old, new, err in errors:
            print(f"  {old} -> {new}: {err}")

    print(f"\nDone. {len(renames) - len(errors)} files renamed, {len(errors)} errors.")
else:
    print(f"\nRun with --execute to perform renames and write files.")
