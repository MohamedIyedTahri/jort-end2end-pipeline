# Phase 4: Modeling

## Overview

In the Modeling phase, we **design and implement the extraction pipeline** that transforms clean text into structured business data. This includes building regex pattern libraries, NLP enrichment strategies, and production-ready extraction code.

---

## Contents

1. **[Extraction Architecture](./EXTRACTION_ARCHITECTURE.md)** — Complete pipeline design (9-stage process)
2. **[Pattern Library](./PATTERN_LIBRARY.md)** — Regex patterns for each field type
3. **[NLP Enrichment](./NLP_ENRICHMENT.md)** — spaCy fallback for complex cases
4. **[Implementation Guide](./IMPLEMENTATION_GUIDE.md)** — Code organization and module structure

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **Hybrid Regex+NLP** | Regex for structured, predictable fields; NLP for semantic ambiguity |
| **Field-Level Extraction** | Extract each field independently, then combine (vs. end-to-end extraction) |
| **Confidence Scoring** | Annotate each extracted value with confidence (0-100) |
| **Fallback Strategy** | Try Regex → NLP → Mark as Not Found |
| **Quality Annotations** | Tag each extraction with method used (REGEX/NLP/FRIEND/MANUAL) |

---

## Modeling Approach

### Stage 1: Constitution Filter
```
Input: Cleaned text
Decision: Is this a constitution notice?
Output: Boolean + confidence
```

### Stage 2: Field Extraction - Regex Phase
```
Input: Constitution notice text
Pattern Matching: Apply regex patterns for each field type
Output: Structured fields with confidence scores
```

### Stage 3: Leadership Extraction - Regex Phase
```
Input: Constitution notice + legal form
Pattern Matching: Apply role-specific patterns (Gérant, Président, etc.)
Output: Management structure
```

### Stage 4-6: NLP Enrichment + Friend Validation + Not Applicable Resolution
```
Input: Extracted fields + legal form rules
Processing: Fill gaps, validate, mark N/A fields
Output: Complete, validated record
```

---

## Deliverables from Phase 4

- ✅ Extraction pipeline (9 stages, fully implemented)
- ✅ Pattern library for all field types (100+ patterns)
- ✅ NLP enrichment module (spaCy-based entity extraction)
- ✅ Friend dataset integration (reference data validation)
- ✅ Output JSON schema with quality annotations
- ✅ Unit tests for each pattern
- ✅ Sample extractions with documentation

---

## Implementation Modules

| Module | File | Purpose |
|---|---|---|
| **Cleaner** | `extractor/cleaner.py` | Text normalization and OCR error correction |
| **Parser** | `extractor/parser.py` | Constitution notice detection |
| **Patterns** | `extractor/patterns.py` | Regex pattern library + matching logic |
| **NLP Enrichment** | `extractor/nlp_enrichment.py` | spaCy-based semantic extraction |
| **Enrichment** | `extractor/enrichment.py` | Friend dataset validation + field completion |
| **Main Pipeline** | `main.py` or `run_extraction.py` | Orchestration of all stages |

---

## Quality Targets for Phase 4

- ✅ **Regex Coverage**: >95% of fields extracted via regex (where applicable)
- ✅ **NLP Fallback Usage**: <5% of records require NLP (edge cases)
- ✅ **Confidence Scoring**: All extractions tagged with numerical confidence
- ✅ **Field Completeness**: >95% of applicable fields populated or marked N/A
- ✅ **Code Organization**: Maintainable pattern library, testable modules

---

**Next**: [Phase 5 - Evaluation](../5_Evaluation/README.md)
