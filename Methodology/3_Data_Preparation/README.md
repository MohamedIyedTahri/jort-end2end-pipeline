# Phase 3: Data Preparation

## Overview

In the Data Preparation phase, we **transform raw JORT text into clean, structured data ready for extraction**. This includes encoding handling, OCR error correction, layout reconstruction, and field annotation.

---

## Contents

1. **[Cleaning Pipeline](./CLEANING_PIPELINE.md)** — Text normalization and OCR error handling
2. **[Annotation Guide](./ANNOTATION_GUIDE.md)** — Manual labeled data creation for validation
3. **[Feature Engineering](./FEATURE_ENGINEERING.md)** — Field naming and output schema

---

## Key Activities

| Activity | Input | Output | Purpose |
|---|---|---|---|
| **Encoding Detection** | Raw notice text files | UTF-8 normalized text | Fix mixed encoding errors |
| **OCR Cleaning** | Normalized text | Clean text without artifacts | Remove typos, spacing issues |
| **Layout Reconstruction** | Multi-column text | Column-ordered text | Correct spatial ordering |
| **Annotation** | Cleaned text | Manual field labels (10%) | Create validation dataset |
| **Schema Definition** | Field requirements | Output JSON schema | Standardize output format |

---

## Cleaning Pipeline Summary

### Stage 1: Encoding Detection + Normalization
```
Input:  Raw bytes (mixed UTF-8/Latin-1/CP1252)
       ↓
Detect: Encoding detection via heuristics
       ↓
Normalize: Transcode to UTF-8
       ↓
Output: UTF-8 clean text
```

### Stage 2: OCR Artifact Removal
```
Input:  Raw OCR text ("Dénominatoin:", "SÀRL")
       ↓
Clean:  Fix common OCR errors (character subs, spacing)
       ↓
Output: "Dénomination:", "SARL"
```

### Stage 3: Layout Reconstruction
```
Input:  Text read left-to-right, top-to-bottom
       ↓
Detect: Multi-column layout via blank lines
       ↓
Reorder: Reconstruct reading order (Col1 complete, then Col2)
       ↓
Output: Logical text flow
```

---

## Deliverables from Phase 3

- ✅ Text cleaner module (`cleaner.py`)
- ✅ Encoding detection and fallback strategy
- ✅ OCR error correction rules
- ✅ Manual annotation of ~1,000 records for validation
- ✅ Output schema definition (JSON structure)
- ✅ Data quality validation: Pre-extraction metrics

---

## Quality Gates

Before proceeding to Phase 4 (Modeling), datapreparation must meet:

- ✅ **Text Cleanliness**: >98% of invalid characters removed
- ✅ **Encoding Accuracy**: 100% correct UTF-8 encoding after normalization
- ✅ **Annotation Coverage**: 10% of 2004 data (1,000 notices) manually annotated
- ✅ **Schema Completeness**: Output schema covers 95%+ of expected fields
- ✅ **Reproducibility**: All cleaning steps are logged and auditable

---

**Next**: [Phase 4 - Modeling](../4_Modeling/README.md)
