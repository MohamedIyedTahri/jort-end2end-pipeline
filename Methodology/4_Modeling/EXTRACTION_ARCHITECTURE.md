# Extraction Architecture

## Complete 9-Stage Pipeline

```
RAW JORT TEXT
      ↓
   [STAGE 1: ENCODING DETECTION]
   Multiple encoding fallback (UTF-8 → CP1252 → Latin-1)
      ↓
   [STAGE 2: TEXT CLEANING]
   OCR artifact removal, spacing normalization, hyphenation fixing
      ↓
   [STAGE 3: CONSTITUTION FILTER]
   Identify if text is a valid constitution notice (keywords + structure)
      ↓
   [STAGE 4: FIELD EXTRACTION - REGEX PHASE]
   Apply patterns to extract structured fields
   (Dénomination, Capital, Siège, Durée, Forme Juridique, Objet)
      ↓
   [STAGE 5: LEADERSHIP EXTRACTION - REGEX PHASE]
   Apply role-specific patterns based on legal form
   (Gérant for SARL/SUARL, Président/PDG for Anonyme, etc.)
      ↓
   [STAGE 6: NLP ENRICHMENT]
   spaCy entity extraction for fields missed by regex
   (Names, addresses, organization entities)
      ↓
   [STAGE 7: FRIEND VALIDATION]
   Cross-check extracted data against Friend reference dataset
   Fill gaps using Friend data (if available)
      ↓
   [STAGE 8: NOT APPLICABLE RESOLUTION]
   Mark fields as "N/A" based on legal form rules
   SUARL: no Président → N/A
   SARL: no Commissaire aux Comptes → N/A (optional role)
      ↓
   [STAGE 9: OUTPUT FORMATTING]
   Create structured JSON with quality annotations
      ↓
STRUCTURED JSON OUTPUT
```

---

## Detailed Stage Descriptions

### STAGE 1: Encoding Detection

**Purpose**: Convert raw bytes to UTF-8, handling mixed encodings in JORT documents

**Algorithm**:
```python
def detect_and_normalize_encoding(raw_bytes):
    # Try UTF-8 first
    try:
        return raw_bytes.decode('utf-8'), 'UTF-8'
    except:
        pass
    
    # Try CP1252 (Windows encoding)
    try:
        result = raw_bytes.decode('cp1252')
        if has_high_entropy(result):  # Quality check
            return result, 'CP1252'
    except:
        pass
    
    # Fall back to Latin-1 (always succeeds)
    return raw_bytes.decode('latin-1', errors='replace'), 'LATIN-1'
```

**Input**: Raw text file bytes
**Output**: UTF-8 normalized text string
**Quality Check**: Validate output contains >95% recognizable characters

---

### STAGE 2: Text Cleaning

**Purpose**: Remove OCR artifacts, normalize spacing, fix hyphenation

**Transformations**:
```
OCR Character Substitution:
  Dénominatoin  →  Dénomination    (i/o swap)
  SÀRL          →  SARL             (accented L)
  Capital:      →  Capital:         (remove extra spaces)
  50 000 DT     →  50000 DT         (normalize spacing in numbers)

Hyphenation Fixing:
  Dénomina-
  tion          →  Dénomination     (join split lines)

Artifact Removal:
  Capital: 50000 DT [PAGE BREAK] Capital...  →  Capital: 50000 DT [...remove duplicate...]
```

**Input**: UTF-8 text
**Output**: Clean text
**Metric**: Validate >95% of OCR artifacts removed (measured on labeled test set)

---

### STAGE 3: Constitution Filter

**Purpose**: Identify if document is a valid constitution notice (vs. other JORT content)

**Decision Logic**:
```python
def is_constitution_notice(text):
    # Check for mandatory constitution keywords
    keywords = ['constitution', 'avi', 'dénomination', 'capital social', 'gérant', 'président']
    
    # Must have 90%+ of keywords
    match_count = sum(1 for kw in keywords if kw in text.lower())
    
    if match_count >= len(keywords) * 0.9:
        return True, confidence=0.95
    elif match_count >= len(keywords) * 0.7:
        return True, confidence=0.70
    else:
        return False, confidence=0.05
```

**Input**: Clean text
**Output**: Boolean (is_constitution), confidence (0-100)
**Quality Target**: >99% of true constitutions identified (high recall)

---

### STAGE 4: Field Extraction - Regex Phase

**Purpose**: Extract structured business fields using regex patterns

**Field Patterns**:
```python
FIELD_PATTERNS = {
    'dénomination': r"[Dd]énomination\s*:?\s*([^\n]+?)(?=\n|Siège|Capital)",
    'forme_juridique': r"[Ff]orme.*?:\s*(SARL|SA|Anonyme|SUARL)"
    'capital': r"[Cc]apital.*?:([\d\s.]+)\s*(?:DT|Dinars)?",
    'siège': r"[Ss]iège.*?:\s*([^\n]+?)(?=\n|Durée|Objet)",
    'durée': r"[Dd]urée\s*:?\s*(\d+)\s*(?:ans?|années?)",
    'objet': r"[Oo]bjet.*?:\s*([^\n]+?)(?=\n|Gérant|Président)",
}
```

**Pattern Feature**:
- Optional whitespace before/after keywords
- Multiple case variants (Dénomination, dénomination, DÉNOMINATION)
- Fuzzy character matching (allow 1-2 OCR substitutions)
- Lazy quantifiers to stop at next field

**Input**: Clean text, form_type (SARL/Anonyme/SUARL)
**Output**: Extracted fields with confidence scores
**Quality Target**: >95% precision, >90% recall per field

---

### STAGE 5: Leadership Extraction - Regex Phase

**Purpose**: Extract management team based on legal form and role patterns

**Role Patterns** (conditional on legal form):
```python
ROLE_PATTERNS = {
    'gérant': r"[Gg]érant\s*:?\s*([Mm]\.?\s*)?([A-Zàèéêôù][a-zàèéêôù]+)\s+([A-Zàèéêôù][a-zàèéêôù]+)",
    'président': r"[Pp]résident\s*:?\s*([Mm]\.?\s*)?([A-Zàèéêôù][a-zàèéêôù]+)\s+([A-Zàèéêôù][a-zàèéêôù]+)",
    'président_dg': r"[Pp]rés.*[Dd]ir.*[Gg]én.*:.*?([A-Z][a-zàèéêôù]+\s+[A-Z][a-zàèéêôù]+)",
    'commissaire_comptes': r"[Cc]ommissaire.*[Cc]omptes\s*:?\s*(.+?)(?=\n|Tribunal)",
}

# Apply based on legal form
if form == 'SARL':
    leadership['gérant'] = extract_role('gérant', text)
elif form == 'Anonyme':
    leadership['président'] = extract_role('président', text)
    leadership['dg'] = extract_role('président_dg', text)
    leadership['commissaire_comptes'] = extract_role('commissaire_comptes', text)
```

**Input**: Clean text, legal form, extracted fields
**Output**: Management structure (names, titles)
**Quality Target**: >90% accuracy for single manager (SARL), >85% for boards (Anonyme)

---

### STAGE 6: NLP Enrichment

**Purpose**: Use spaCy to extract entities missed by regex (fallback)

**Approach**:
```python
import spacy

nlp = spacy.load("fr_core_news_sm")

def nlp_enrichment(text, extracted_fields):
    doc = nlp(text)
    
    # Extract PERSON entities (for names)
    persons = [ent.text for ent in doc.ents if ent.label_ == 'PERSON']
    
    # Extract GPE entities (for locations/addresses)
    locations = [ent.text for ent in doc.ents if ent.label_ in ['GPE', 'LOC']]
    
    # Fill missing fields if confidence is high
    if not extracted_fields.get('dénomination') and doc.ents:
        # Heuristic: first ORG entity might be company name
        orgs = [ent.text for ent in doc.ents if ent.label_ == 'ORG']
        if orgs:
            extracted_fields['dénomination'] = orgs[0]
            extracted_fields['dénomination_method'] = 'NLP'
    
    if not extracted_fields.get('gérant') and persons:
        # Take first person entity and assume it's gérant
        extracted_fields['gérant'] = persons[0]
        extracted_fields['gérant_method'] = 'NLP'
    
    return extracted_fields
```

**Input**: Clean text, partially extracted fields
**Output**: Filled fields from NLP entities
**Quality Target**: High precision (>95%) but low coverage (<5% of records need NLP)

---

### STAGE 7: Friend Validation

**Purpose**: Cross-check and fill missing data using Friend reference dataset

**Approach**:
```python
def friend_validation(extracted, friend_record):
    # Compare extracted vs Friend for validation
    match_score = calculate_similarity(extracted['dénomination'], friend_record['name'])
    
    if match_score > 0.95:  # High confidence match
        # Fill missing fields from Friend
        for field in ['capital', 'siège', 'gérant']:
            if not extracted.get(field):
                extracted[field] = friend_record[field]
                extracted[f'{field}_source'] = 'FRIEND'
        
        return extracted, validation_status='MATCHED'
    
    elif match_score > 0.80:
        # Possible match; flag for review
        return extracted, validation_status='POSSIBLE_MATCH'
    
    else:
        # No match found; use extracted data as-is
        return extracted, validation_status='NO_MATCH'
```

**Input**: Extracted fields, Friend reference dataset
**Output**: Validated/enriched fields with source tracking
**Quality Target**: >95% precision in validation (low false positives)

---

### STAGE 8: Not Applicable Resolution

**Purpose**: Mark legally inapplicable fields as "N/A" based on form rules

**Legal Form Rules**:
```python
NOT_APPLICABLE_RULES = {
    'SUARL': ['conseil_administration', 'président', 'vice_président'],
    'SARL': ['conseil_administration', 'président', 'vice_président', 'commissaire_comptes_mandatory'],
    'Anonyme': ['gérant'],
}

def resolve_na_fields(extracted, form):
    na_fields = NOT_APPLICABLE_RULES.get(form, [])
    
    for field in na_fields:
        if not extracted.get(field) or extracted[field] is None:
            extracted[field] = 'N/A'
            extracted[f'{field}_reason'] = 'NOT_APPLICABLE_FOR_FORM'
    
    return extracted
```

**Input**: Extracted fields, legal form
**Output**: Complete record with N/A marked appropriately
**Quality Target**: 100% compliance with legal form rules

---

### STAGE 9: Output Formatting

**Purpose**: Format as structured JSON with quality annotations

**Output Schema**:
```json
{
  "source": {
    "jort_year": 2004,
    "jort_issue": "001Journal_annonces2004",
    "document_date": "2004-01-15"
  },
  "extraction": {
    "extracted_at": "2024-01-20T15:30:45Z",
    "pipeline_version": "1.0",
    "total_confidence": 92,
    "fields_found": 9,
    "fields_not_applicable": 2
  },
  "company": {
    "dénomination": {
      "value": "Acme Technologies SARL",
      "confidence": 99,
      "method": "REGEX"
    },
    "forme_juridique": {
      "value": "SARL",
      "confidence": 99,
      "method": "REGEX"
    },
    "capital_social": {
      "value": "50000",
      "currency": "DT",
      "confidence": 95,
      "method": "REGEX"
    },
    "siège_social": {
      "value": "123 Rue de Carthage, Tunis 1000",
      "confidence": 87,
      "method": "REGEX"
    },
    "durée": {
      "value": 50,
      "unit": "ans",
      "confidence": 98,
      "method": "REGEX"
    },
    "objet_social": {
      "value": "Développement de logiciels et services informatiques",
      "confidence": 85,
      "method": "REGEX"
    }
  },
  "management": {
    "gérant": {
      "value": "Ahmed Ben Ali",
      "confidence": 88,
      "method": "REGEX"
    },
    "président": {
      "value": "N/A",
      "confidence": 100,
      "reason": "NOT_APPLICABLE_FOR_FORM_SARL"
    }
  },
  "validation": {
    "friend_match": "MATCHED",
    "friend_match_score": 0.97,
    "quality_status": "READY_FOR_USE"
  }
}
```

**Input**: All extracted fields from Stages 1-8
**Output**: Structured JSON
**Quality Target**: 100% valid JSON, all fields documented

---

## End-to-End Example

**Input**: Raw JORT text (encoded, with OCR errors)
```
Dénominatoin: Acmé SARL
Siège: 123 rue Carthage, Tunis
Capital social: 50 000 DT
Durée: 50 ans ou 99 ans
Gérant:
M. Ahmed Ben Ali
```

**After Stage 1-2**: Clean UTF-8, OCR fixed
```
Dénomination: Acme SARL
Siège: 123 Rue Carthage, Tunis
Capital social: 50000 DT
Durée: 50 ans
Gérant: M. Ahmed Ben Ali
```

**After Stage 4-5**: Regex extraction
```json
{
  "company": {
    "dénomination": {"value": "Acme SARL", "confidence": 99, "method": "REGEX"},
    "forme_juridique": {"value": "SARL", "confidence": 99, "method": "REGEX"},
    "capital_social": {"value": "50000", "confidence": 95, "method": "REGEX"},
    "siège_social": {"value": "123 Rue Carthage, Tunis", "confidence": 87, "method": "REGEX"}
  },
  "management": {
    "gérant": {"value": "Ahmed Ben Ali", "confidence": 88, "method": "REGEX"}
  }
}
```

**After Stage 8**: N/A resolution
```json
{
  ...existing fields...,
  "management": {
    "gérant": {"value": "Ahmed Ben Ali", "confidence": 88, "method": "REGEX"},
    "président": {"value": "N/A", "confidence": 100, "reason": "NOT_APPLICABLE_FOR_FORM_SARL"}
  }
}
```

---

## Quality Metrics by Stage

| Stage | Input Metric | Output Metric | Target |
|---|---|---|---|
| 1 | Raw bytes | UTF-8 encoding | 100% |
| 2 | OCR error rate: 5-15% | Clean text error rate: <1% | >99% artifacts removed |
| 3 | Unknown if constitution | Constitution identified | >99% recall |
| 4-5 | No structured fields | Field extraction rate | >90% recall, >95% precision |
| 6 | Regex coverage: ~95% | NLP coverage: remaining 5% | <2% unextracted |
| 7 | Unvalidated data | Validated + enriched | >95% match rate with Friend |
| 8 | Incomplete records | Complete with N/A | 100% field coverage |
| 9 | Structured data | Formatted JSON | 100% valid, all annotated |

---

**See Also**:
- [Pattern Library](./PATTERN_LIBRARY.md) — Detailed regex patterns for each field
- [NLP Enrichment](./NLP_ENRICHMENT.md) — spaCy configuration and entity extraction
- [Implementation Guide](./IMPLEMENTATION_GUIDE.md) — Code structure and module organization
