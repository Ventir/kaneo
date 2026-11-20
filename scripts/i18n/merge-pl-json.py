#!/usr/bin/env python3
"""Scalanie trójstronne i18n/pl-PL.json po aktualizacji Kaneo z upstreamu.

Uruchamiaj w katalogu repo Kaneo, w trakcie `git merge <upstream>` z konfliktem w i18n/pl-PL.json
(en-US.json musi być już scalony bez konfliktu):

    python3 scripts/i18n/merge-pl-json.py --theirs upstream/main [--report pl-merge-raport.md]

Zasady:
- struktura i kolejność kluczy: upstreamowy pl-PL.json (ma już formy _few/_many);
- klucz przetłumaczony u nas -> zostaje nasze tłumaczenie; jeśli zmienił się tekst en-US,
  klucz trafia do raportu „EN zmieniony”;
- klucz nowy w upstreamie -> wartość z upstreamowego pl-PL (zwykle tłumaczenie maszynowe
  albo angielski), raport „nowe”;
- klucz dodany tylko w forku (np. common:demo.*) zostaje, jeśli jest w scalonym en-US;
- klucz, którego nie ma już w scalonym en-US -> znika (raport „usunięte”).
Wynik zapisuje do i18n/pl-PL.json. Potem: przejrzyj raport, popraw teksty, `pnpm i18n:check`.
"""
import argparse, json, re, subprocess, sys

PL, EN = "i18n/pl-PL.json", "i18n/en-US.json"
PLURAL = re.compile(r"_(zero|one|two|few|many|other)$")

def show(ref, path):
    out = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True)
    return json.loads(out.stdout) if out.returncode == 0 else {}

def flat(d, p=""):
    r = {}
    for k, v in d.items():
        key = f"{p}.{k}" if p else k
        r.update(flat(v, key) if isinstance(v, dict) else {key: v})
    return r

def en_text(en, key):
    """Tekst angielski dla klucza, także dla form liczby mnogiej, których en-US nie ma."""
    if key in en:
        return en[key]
    stem = PLURAL.sub("", key)
    for cand in (f"{stem}_other", f"{stem}_one", stem):
        if cand in en:
            return en[cand]
    return None

def set_path(d, key, value):
    parts = key.split(".")
    for p in parts[:-1]:
        d = d.setdefault(p, {})
    d[parts[-1]] = value

ap = argparse.ArgumentParser()
ap.add_argument("--theirs", required=True, help="ref upstreamu, np. upstream/main")
ap.add_argument("--ours", default="HEAD")
ap.add_argument("--base", help="domyślnie git merge-base ours theirs")
ap.add_argument("--report", default="pl-merge-raport.md")
a = ap.parse_args()
base = a.base or subprocess.run(["git", "merge-base", a.ours, a.theirs], capture_output=True, text=True).stdout.strip()

try:
    en_new = flat(json.load(open(EN, encoding="utf-8")))
except json.JSONDecodeError:
    sys.exit("i18n/en-US.json ma konflikt albo jest uszkodzony. Najpierw rozwiąż en-US.json.")
en_base = flat(show(base, EN))
pl_ours, pl_theirs_tree = flat(show(a.ours, PL)), show(a.theirs, PL)
pl_theirs = flat(pl_theirs_tree)
if not pl_ours or not pl_theirs:
    sys.exit("Nie udało się odczytać pl-PL.json z podanych refów.")

merged_tree, merged = {}, {}
new_keys, en_changed, removed = [], [], []
order = list(pl_theirs) + [k for k in pl_ours if k not in pl_theirs]
for key in order:
    en = en_text(en_new, key)
    if en is None:
        if key in pl_ours:
            removed.append(key)
        continue
    if key in pl_ours:
        value = pl_ours[key]
        old_en = en_text(en_base, key)
        if old_en is not None and old_en != en:
            en_changed.append(key)
    else:
        value = pl_theirs[key]
        new_keys.append(key)
    merged[key] = value
    set_path(merged_tree, key, value)

english_left = [k for k, v in merged.items()
                if isinstance(v, str) and v == en_text(en_new, k) and re.search(r"[A-Za-z]{3}", v)]

with open(PL, "w", encoding="utf-8") as f:
    f.write(json.dumps(merged_tree, ensure_ascii=False, indent="\t") + "\n")

def section(title, keys, with_text=True):
    lines = [f"## {title} ({len(keys)})", ""]
    for k in keys:
        lines.append(f"- `{k}`: EN „{en_text(en_new, k)}” → PL „{merged[k]}”" if with_text else f"- `{k}`")
    return lines + [""]

rep = ["# Raport scalania pl-PL.json", "", f"base `{base[:10]}`, ours `{a.ours}`, theirs `{a.theirs}`", ""]
rep += section("Nowe klucze z upstreamu, do przejrzenia", new_keys)
rep += section("Zmieniony tekst angielski, sprawdź nasze tłumaczenie", en_changed)
rep += section("Wartość identyczna z angielską (część jest poprawna, np. nazwy własne)", english_left)
rep += section("Usunięte (nie ma ich już w en-US)", removed, with_text=False)
with open(a.report, "w", encoding="utf-8") as f:
    f.write("\n".join(rep))
print(f"nowe: {len(new_keys)}, EN zmieniony: {len(en_changed)}, "
      f"identyczne z EN: {len(english_left)}, usunięte: {len(removed)} -> {a.report}")
