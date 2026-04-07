# evaluate_missing_vs_not_applicable.py

import json
from collections import defaultdict
import os

# Path to the JSON dataset
json_file = os.path.join("output", "extracted_notices.json")

# Load data
with open(json_file, "r", encoding="utf-8") as f:
    notices = json.load(f)

# Core fields expected by downstream consumers.
CORE_FIELDS = [
    "company_name",
    "capital",
    "address",
    "corporate_purpose",
    "duration",
    "manager",
]

# Initialize dictionaries.
total_by_form = defaultdict(int)
missing_counts = defaultdict(lambda: defaultdict(int))
not_applicable_counts = defaultdict(lambda: defaultdict(int))

# Loop through each notice.
for notice in notices:
    legal_form = notice.get("legal_form", "unknown")
    total_by_form[legal_form] += 1
    not_applicable_fields = set(notice.get("not_applicable_fields") or [])

    for field in CORE_FIELDS:
        if field in not_applicable_fields:
            not_applicable_counts[legal_form][field] += 1
        elif notice.get(field) is None:
            missing_counts[legal_form][field] += 1

# Print summary by legal form.
for legal_form in sorted(total_by_form.keys()):
    total = total_by_form[legal_form]
    print(f"\nLegal form: {legal_form} (Total notices: {total})")

    print(" Missing values (field applicable but not extracted):")
    for field in CORE_FIELDS:
        count = missing_counts[legal_form][field]
        print(f"  - {field}: {count} ({count/total:.2%})")

    print(" Not applicable (field absent by notice/legal-form structure):")
    for field in CORE_FIELDS:
        count = not_applicable_counts[legal_form][field]
        print(f"  - {field}: {count} ({count/total:.2%})")