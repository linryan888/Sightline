"""
Fill in a ratings file from a string of digits, one 1-5 rating per window, in order.

    python fill_ratings.py out/ratings_template.csv ratings.csv 3425153...

Spaces and commas in the digits are ignored. The number of digits must equal the number of windows
in the template (the numbers on the contact sheet go from 1 to that count).
"""

import csv
import sys


def main():
    if len(sys.argv) < 4:
        sys.exit("usage: python fill_ratings.py TEMPLATE.csv OUT.csv DIGITS")
    template, out, digits = sys.argv[1], sys.argv[2], "".join(sys.argv[3:])
    digits = [c for c in digits if c not in " ,;\n"]
    with open(template, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if len(digits) != len(rows):
        sys.exit(f"The template has {len(rows)} windows but you gave {len(digits)} digits.")
    if any(d not in "12345" for d in digits):
        sys.exit("Every rating must be a digit from 1 to 5.")
    for r, d in zip(rows, digits):
        r["rating"] = d
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["video", "start_seconds", "end_seconds", "rating"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out} with {len(rows)} ratings")


if __name__ == "__main__":
    main()
