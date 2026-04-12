# Data Inventory

## JORT Source Data Overview

### Publication Context

**JORT (Journal Officiel de la République Tunisienne)** is the official gazette of the Tunisian Republic, publishing all legal and administrative announcements.

| Property | Value |
|---|---|
| **Publisher** | Tunisian Government / Imprimerie Officielle |
| **Frequency** | Daily (5-7 days per week) |
| **Availability** | Archives back to 1956 (paper); digital 2000+  |
| **Format Evolution** | PDF since ~2000; scanned images until ~2010; born-digital 2010+ |
| **Access** | Public; archives available through Official Gazette website |

---

## Constitution Notice Data Structure

### Definition

A **constitution notice** (avis de constitution) is a mandatory announcement when a new business is formed. It contains:
- Company identifiers (name, legal form)
- Capital structure
- Management team
- Physical address
- Registered office information

### Legal Framework

Tunisian law (Code du Commerce) requires all new businesses to publish a constitution notice in JORT within 30 days of registration. The notice must include standardized fields.

### Data Organization

```
constitution/
├── anonyme/          (Société Anonyme - joint-stock companies)
│   └── 2004/
│       ├── 001Journal.../notice.txt
│       ├── 002Journal.../notice.txt
│       └── ...
├── sarl/             (SARL - limited liability companies)
│   └── 2004/
│       ├── 001Journal.../notice.txt
│       └── ...
├── suarl/            (SUARL - single-person LLC)
│   └── 2004/
│       ├── 001Journal.../notice.txt
│       └── ...
└── autre/            (Other legal forms)
    └── 2004/
        └── ...
```

### Legal Forms

| Form | Acronym | English | Characteristics | Count (2004) |
|---|---|---|---|---|
| **Anonyme** | SA | Joint-Stock Company | Board of directors, public offering-capable | ~2,000 |
| **SARL** | SARL | Limited Liability Company | One or more partners with limited liability | ~7,000 |
| **SUARL** | SUARL | Single-Person LLC | Single founder, simplified structure | ~900 |
| **Autre** | N/A | Other forms | Associations, partnerships, etc. | ~100 |
| **TOTAL 2004** | | | | ~10,000 |

---

## Key Data Fields

### Standard Extracted Fields

| Field | Data Type | Example | Presence Rate |
|---|---|---|---|
| **Dénomination** | String | "Acme Technologies SARL" | 100% |
| **Forme Juridique** | Category | SARL, Anonyme, SUARL | 100% |
| **Siège Social** | Address | "123 Rue de Carthage, Tunis 1000" | 98% |
| **Capital Social** | Amount (DT) | "50000 DT" | 99% |
| **Durée** | Number (years) | "50 ans" | 95% |
| **Objet Social** | Text | "Développement de logiciels" | 85% |
| **Gérant** | Name (SARL/SUARL) | "M. Ahmed Ben Ali" | 95% |
| **Président** | Name (Anonyme) | "Mme Fatima Bensalah" | 92% (if Anonyme) |
| **Directeur Général** | Name (Anonyme) | "M. Ali Zaiem" | 88% (if Anonyme) |
| **Commissaire aux Comptes** | Name/Entity | "Cabinet Audit XYZ" | 45% |
| **Tribunal d'Enregistrement** | Jurisdiction | "Tribunal de Tunis" | 70% |
| **Numéro Registre Commercial** | Identifier | "RC-12345" | 80% |

### Derived / Metadata Fields

| Field | Source | Type |
|---|---|---|
| **Extraction Date** | Derived | Timestamp when record was extracted |
| **Source Document** | Metadata | Reference to original JORT issue |
| **Quality Score** | Derived | 0-100 confidence in extraction |
| **Extraction Method** | Derived | "REGEX" / "NLP" / "MANUAL" |

---

## Data Scale & Scope

### 2004 Baseline (Phase 1)

```
2004 JORT Constitution Notices:
├── Valid notices to extract: ~9,800
├── Duplicate notices: ~50 (same company, multiple publications)
├── Non-constitution notices: ~150 (modifications accidentally included)
└── Total in archive: ~10,000
```

### Multi-Year Scaling (Future Phases)

| Year | Estimated Notices | Growth Note |
|---|---|---|
| 2004 | ~10,000 | Baseline; older scans |
| 2005-2009 | ~12,000/year | Steady growth; improving OCR quality |
| 2010-2015 | ~15,000/year | Digital transition; best OCR quality |
| 2016-2020 | ~14,000/year | Economic slowdown (COVID) |
| 2021-2025 | ~13,000/year | Post-COVID recovery |
| **TOTAL 2004-2025** | **~295,000** | Full dataset target |

---

## Data Quality Characteristics

### OCR Quality by Decade

| Period | Scan Type | OCR Quality | Challenge Level |
|---|---|---|---|
| **2004-2009** | Scanned images | 70-85% character accuracy | High (primary source of errors) |
| **2010-2015** | Mixed scans/digital | 85-95% character accuracy | Medium |
| **2016-2025** | Born-digital | 95%+ character accuracy | Low |

### Encoding Patterns

Observed encoding distribution in 2004 notices:

```
UTF-8     (modern, correct):        40%
Latin-1   (Windows inherited):      35%
CP1252    (very old Windows):       15%
Garbled   (encoding errors):        10%
```

### Layout Characteristics

- **Single-Column**: ~20% (simpler documents)
- **Dual-Column**: ~70% (standard JORT format)
- **Multi-Column (3+)**: ~10% (special issues)
- **RTL Text Mixing**: ~100% (Arabic headings present)
- **Tabular Content**: ~30% (management lists formatted as tables)

---

## Data Source Inventory

### Filesystem Organization

| Directory | Purpose | File Count | Size |
|---|---|---|---|
| `/constitution/anonyme/2004/` | SA companies | ~2,000 | ~40 MB |
| `/constitution/sarl/2004/` | SARL companies | ~7,000 | ~140 MB |
| `/constitution/suarl/2004/` | SUARL companies | ~900 | ~18 MB |
| `/constitution/autre/2004/` | Other forms | ~100 | ~2 MB |
| **TOTAL** | | **~10,000** | **~200 MB** |

### Reference Datasets

| Dataset | Purpose | Size | Quality |
|---|---|---|---|
| **Friend 2004** | Validation/ground truth | ~1,500 records | 100% accuracy (manually verified) |
| **OCR Baseline** | Quality measurement | Random sample: 100 | Measured ~78% character accuracy |

---

## Data Access & Privacy

### Public Nature of Data

- ✅ All data comes from public JORT announcements
- ✅ Published information; no privacy restrictions
- ✅ Historical data fully available

### Data Protection Implications

- Contains personal names of business founders/managers
- Must establish data governance for downstream applications
- PII handling: Consider anonymization for public-facing products (future phase)

---

## Data Characteristics Summary

| Dimension | Characteristic | Impact |
|---|---|---|
| **Volume** | ~10,000 notices/year | Manageable for batch processing; parallelizable |
| **Variety** | Multiple legal forms, field formats | Need flexible extraction rules |
| **Velocity** | Historical batch + daily new (future) | Start with batch; can add streaming later |
| **Veracity** | Variable OCR quality, encoding issues | Need robust error handling |
| **Legal** | Fully public announcements | No privacy barriers; good for monetization |
| **Age** | Up to 20 years old (2004-2025) | Older scans have more OCR errors |

---

## Recommendations for Phase 2 → Phase 3 Transition

1. **Encoding Handling**: Build cascading detection (UTF-8 → CP1252 → Latin-1)
2. **OCR Robustness**: Use fuzzy matching in regex; allow character substitutions
3. **Layout Awareness**: Leverage spatial coordinates from PDF API
4. **Field Variability**: Build regex patterns as alternatives, not single match
5. **Validation**: Reserve 10% of 2004 data as validation set (held out from pattern tuning)

---

**Next**: [Quality Baseline](./QUALITY_BASELINE.md) — Detailed quality assessment findings
