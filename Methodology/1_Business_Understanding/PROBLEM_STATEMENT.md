# Problem Statement

## The Core Problem

**JORT (Journal Officiel de la République Tunisienne) publishes thousands of legally binding business announcements daily, but these announcements are inaccessible for automated analysis. Today, extracting business intelligence from JORT requires expensive, error-prone manual work—or is not done at all.**

---

## Why This Problem Matters

### The Paradox

```
JORT contains precise, structured business data that economists, 
investors, and regulators urgently need, but...

Published in unstructured PDF → Not accessible to analysis
→ Represents lost economic intelligence
```

**Example**: A Tunisian economist wants to understand how many tech startups were formed in Tunis in 2004, their total capitalization, and typical team size. This information exists in JORT, but requires manually reading through hundreds of pages of PDFs.

### Economic Impact

- **For Government**: Cannot generate automated economic reports from JORT; missing data for policy decisions
- **For Business**: Cannot track market trends or competitors systematically; high cost of business intelligence
- **For Investors**: Cannot discover new opportunities algorithmically; missing deal sourcing capability
- **For Citizens**: JORT announcements are legally binding but practically inaccessible; business registry divorced from official journal

---

## Root Causes: Why Extraction Is Hard

### 1. **Text Format & Layout Challenges**

#### Multi-Column Layout
- JORT PDFs organize text in 2-3 columns
- Column content is spatially separated, not logically ordered
- PDF readers reconstruct text by reading left-to-right, top-to-bottom → garbled order

```
PDF Layout:          Logical Order Needed:
┌─────────┬─────────┐
│ Col 1   │ Col 2   │    Col1_line1 → Col2_line1 (next page)
│ text... │ text... │    Col1_line2 → Col2_line2 (next page)
│ text... │ text... │    etc.
└─────────┴─────────┘

Naive Reading:       Correct Reading:
Col1_text,          Col1_text (full column),
Col2_text           THEN Col2_text (full column)
```

#### Right-to-Left (RTL) Text Mixing
- Arabic text mixed with French text in same document
- RTL text requires special handling; standard tools assume left-to-right

---

### 2. **OCR Quality Degradation**

Constitution notices span decades (2004 onward):
- **2004-2010**: Scanned from original documents; medium to poor quality
- **2010-2020**: Born-digital PDFs; generally good quality
- **2020+**: High-quality digital publishing

#### OCR Errors Typical in Old Scans
```
Intended:   "Dénomination: Acme SARL"
Scanned As: "Dénomination: Acmé SARL"  [accent error]
Or:         "Dénomination: Acme SÀRL"  [character swap]
Or:         "Dénomination: Acme SAR|"  [pipe instead of L]
```

---

### 3. **Encoding Inconsistencies**

JORT data uses multiple character encodings without clear indication:

| Encoding | Use Case | Problem |
|---|---|---|
| **UTF-8** | Modern documents | Default, works fine |
| **Latin-1** | Older documents (Windows) | Accent characters (é, à, î) misinterpreted |
| **CP1252** | Very old documents | Special chars become garbage |

**Example**: 
```
UTF-8:    "Décision"     (correct, accented é)
Latin-1:  "DÃ©cision"    (mojibake: 2 chars instead of 1)
Read as:  "Deci sion"    (lost semantic meaning)
```

**Impact**: Regex patterns fail to match because input characters don't match expected patterns.

---

### 4. **Inconsistent Formatting**

Legal notices lack standardized structure within JORT:

#### Field Variability
```
Variant 1: "Dénomination: Acme SARL"
Variant 2: "Dénomination : Acme SARL"    (space before colon)
Variant 3: "Dénomination...Acme SARL"     (dots instead of colon)
Variant 4: "SARL Acme"                    (reversed order)
```

#### Management Structure Variations
```
Single Founder (SUARL):
"Gérant: M. Ahmed Ben Ali"

Board Structure (Anonyme):
"Président: Mme Fatima Bensalah
Directeur Général: M. Ali Zaiem
Commissaire aux comptes: Cabinet XYZ"

Dual Founder (SARL):
"Gérant 1: M. Mohamed Ahmed
Gérant 2: Mme Leila Zaiem"
```

Without knowing the legal form in advance, extracting the right management team is ambiguous.

---

### 5. **Semantic Ambiguity**

Legal terminology is domain-specific and sometimes ambiguous:

| Term | Meaning | Ambiguity |
|---|---|---|
| **Gérant** | Manager (SARL) | Can refer to single manager or multiple |
| **Président** | President (Anonyme) | May also appear in other contexts |
| **Directeur Général** | Chief Executive Officer | May be abbreviated as DG or PDG (Président Directeur Général) |
| **Siège** | Head Office / Registered Address | Can be confused with meeting room (salle de siège) |
| **Capital** | Share capital | May be stated in DT (Tunisian Dinar), Euros, or other currency |

**Example Challenge**:
```
Text: "M. Ahmed Ben Ali, résidant à Tunis, Directeur"

Is this:
A) Ahmed is the Director (Directeur Général)?
B) Ahmed is the registered address (wrong interpretation)?
C) Ahmed is the auditor?

Answer depends on company legal form (unknown at this point).
```

---

### 6. **Data Quality Issues Specific to Legal Documents**

#### Abbreviation Variability
```
Titles:      Mme / Madame / Mlle / Mademoiselle / Miss
             Mr / Monsieur / M / Messrs
             Dr / Doctor / Docteur

Company Forms: SARL / Sarl / S.A.R.L. / Sté à Responsabilité Limitée
               Anonyme / SA / S.A. / Société Anonyme

Roles:       PDG / P.D.G. / Pdt / Pdt. / Président Directeur Général
```

#### Address Ambiguity
```
"123 rue de Carthage, Apt 5, Tunis 1000"
→ Is "1000" the postal code or part of address?

"lotissement Tunis, Bloc 3, Tunis"
→ Multiple locations named "Tunis"; which one?
```

---

## Existing Approaches & Their Limitations

| Approach | Pros | Cons | Verdict |
|---|---|---|---|
| **Manual Data Entry** | 100% accurate | Costs $500-1000/day per person; 10+ notices per day max; not scalable | ❌ Not viable |
| **Naive PDF Text Extraction** | Simple to implement | Fails on multi-column layout, encoding, OCR noise → ~50% accuracy | ❌ Too inaccurate |
| **Commercial OCR Tool** | Better character recognition | Still doesn't handle layout, encoding, semantic ambiguity; very expensive | ❌ Insufficient |
| **Rule-Based Regex Patterns** | Interpretable, updatable, fast | Requires domain expertise; needs careful pattern tuning; can miss edge cases | ⚠️ Promising but incomplete |
| **Deep Learning (LSTM/Transformer)** | Theoretically handles all complexity | Requires huge labeled dataset (100k+ notices); expensive to train; black box; overkill for this domain | ❌ Not justified |
| **Hybrid Regex + NLP Fallback** | Combines interpretability (regex) + flexibility (NLP); scales with current data | Requires two-pipeline maintenance; NLP fallback adds latency | ✅ **SELECTED** |

---

## Impact of Current Problem

### Current State (Without Solution)

| Impact Area | Consequence |
|---|---|
| **Economic Policy** | Government cannot generate automated economic reports; missing data for evidence-based policy decisions |
| **Business Intelligence** | Companies cannot track market trends; manual research costs thousands per report |
| **Investment Sourcing** | Investors cannot discover opportunities algorithmically; miss deal flow |
| **Legal Tech** | Cannot build applications requiring JORT data; market segment remains untapped |
| **Public Access** | Citizens cannot query business announcements effectively; JORT remains opaque journal |

---

## Problem Scope

### What We're NOT Solving

- ❌ Web scraping or PDF collection (separate pipeline: Direct_Extraction/)
- ❌ OCR technology improvement (using Tesseract as-is)
- ❌ Historical data digitization (starts with already-extracted text)
- ❌ Multi-language processing beyond French+Arabic
- ❌ Document types beyond constitution notices (Phase 1)

### What We ARE Solving

- ✅ Parse semi-structured text from JORT PDFs
- ✅ Extract structured fields (company name, capital, management, etc.)
- ✅ Handle OCR errors and encoding variations
- ✅ Build interpretable, maintainable pattern library
- ✅ Provide quality metrics and validation

---

## Success Criteria for Problem Resolution

A successful solution will:

1. **Extract >95% of applicable fields** from 2004 constitution notices (Friend dataset comparison)
2. **Maintain <3% false positive rate** (no invented data)
3. **Handle encoding/OCR/layout variations** without manual intervention
4. **Be maintainable** (team can update patterns for new variations)
5. **Be explainable** (confidence scores and extraction provenance)
6. **Enable downstream applications** (output feeds economic analytics, BI dashboards)

---

**Next Reading**:
- [Business Objectives](./BUSINESS_OBJECTIVES.md) — How solving this problem enables strategic value
- [Use Cases](./USE_CASES.md) — Real-world applications enabled by extraction
