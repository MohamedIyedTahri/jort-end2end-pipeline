# Quality Framework

## Overview

This document defines **how we measure extraction quality** - the metrics, validation methods, and success criteria for the Infyntra project.

---

## Quality Dimensions

### 1. **Accuracy**

**Definition**: Extracted data matches ground truth.

**Metrics**:
- **Precision**: Of data we extracted, how much is correct?
  - Formula: `Correct / (Correct + False Positives)`
  - Target: >95% (minimize invented/incorrect data)

- **Recall**: Of data that should be extracted, how much did we get?
  - Formula: `Correct / (Correct + False Negatives)`
  - Target: >90% (capture most valid data)

- **F1-Score**: Harmonic mean of precision and recall
  - Formula: `2 * (Precision * Recall) / (Precision + Recall)`
  - Target: >92%

### 2. **Completeness**

**Definition**: All applicable fields are extracted or appropriately marked.

**Metrics**:
- **Field Coverage Rate**: Percentage of applicable fields extracted (not missing)
  - Formula: `Fields Found / Applicable Fields`
  - Target: >95%

- **N/A Correctness**: Fields marked "N/A" are actually not applicable (per legal form rules)
  - Formula: `Correctly Marked N/A / Total N/A Marked`
  - Target: 100%

### 3. **Reliability**

**Definition**: System produces consistent results; low error rate.

**Metrics**:
- **False Positive Rate**: Percentage of extracted data that is incorrect
  - Formula: `False Positives / All Extracted`
  - Target: <3%

- **False Negative Rate**: Percentage of valid data we missed
  - Formula: `False Negatives / All Valid Data`
  - Target: <10%

### 4. **Robustness**

**Definition**: Performance is consistent across data variations.

**Metrics**:
- **Consistency Across OCR Quality**: Accuracy remains similar for poor vs. good OCR
  - Formula: Compare precision on scans (2004) vs. born-digital (2020)
  - Target: <5% variance

- **Consistency Across Legal Forms**: Accuracy similar for SARL vs. Anonyme vs. SUARL
  - Formula: Per-form precision within 5% of overall
  - Target: Form-driven variance <5%

### 5. **Confidence Scoring**

**Definition**: Extracted values are tagged with confidence (0-100).

**Metrics**:
- **Calibration**: Stated confidence matches actual accuracy
  - Formula: Among records with 95% confidence, measure actual accuracy
  - Target: Actual accuracy ≈ Stated confidence (within 5%)

- **Coverage**: All extractions have confidence scores
  - Formula: `Records with confidence / Total records`
  - Target: 100%

---

## Validation Methods

### Method 1: Manual Validation (Ground Truth)

**Process**:
1. Randomly select 100 documents from validation set
2. Manually review extracted fields
3. Compare against what should be extracted
4. Calculate precision, recall per field

**Frequency**: After each major pattern update
**Effort**: ~4 hours per 100 documents
**Cost**: $50-100 per validation round

---

### Method 2: Friend Dataset Comparison

**Process**:
1. Extract all 2004 data using pipeline
2. Match against Friend dataset (~1,500 golden records)
3. Compare field-by-field
4. Calculate match rate and confidence

**Metrics**:
- **Name Matching**: Company name similarity (fuzzy match)
- **Capital Matching**: Exact match or within 5% tolerance
- **Category Matching**: Legal form identity
- **Overall Match Rate**: Percentage of Friend records matched

**Frequency**: Continuous (automatic)
**Effort**: Automated
**Cost**: $0

---

### Method 3: Differential Analysis

**Process**:
1. Compare extractions across different OCR qualities
2. Compare extractions across legal forms
3. Identify systematic biases
4. Document failure modes

**Frequency**: Weekly during active development; monthly in production
**Effort**: ~2 hours per analysis

---

### Method 4: Spot Checks (Production Monitoring)

**Process**:
1. Randomly sample 10 records daily from production extraction
2. Quick manual review of critical fields
3. Flag any anomalies
4. Track error trends over time

**Frequency**: Daily
**Effort**: ~15 minutes/day
**Cost**: Low (automated alerting + spot review)

---

## Field-Level Quality Targets

### Critical Fields (High Priority)

| Field | Precision | Recall | F1-Score | Comments |
|---|---|---|---|---|
| **Dénomination** | 99% | 98% | 98% | Most important; must be accurate |
| **Forme Juridique** | 99% | 99% | 99% | Drives downstream logic |
| **Capital Social** | 98% | 96% | 97% | Valuable for economic analysis |

### Important Fields (Medium Priority)

| Field | Precision | Recall | F1-Score | Comments |
|---|---|---|---|---|
| **Siège Social** | 95% | 90% | 92% | Useful for location analysis; harder to extract |
| **Durée** | 96% | 94% | 95% | Usually present but format varies |
| **Gérant / Président** | 92% | 88% | 90% | Management structure important; complex extraction |

### Supplementary Fields (Lower Priority)

| Field | Precision | Recall | F1-Score | Comments |
|---|---|---|---|---|
| **Objet Social** | 85% | 80% | 82% | Frequently abbreviated; lower priority |
| **Commissaire aux Comptes** | 90% | 70% | 79% | Optional role; lower frequency |
| **Tribunal d'Enregistrement** | 80% | 75% | 77% | Nice-to-have; not critical |

---

## Overall Quality Score

### Calculation

```
Quality_Score = (
    (Precision * 0.35) +
    (Recall * 0.25) +
    (Completeness * 0.20) +
    (Consistency * 0.15) +
    (Confidence_Calibration * 0.05)
) * 100
```

### Interpretation

| Score | Status | Action |
|---|---|---|
| 95-100 | Excellent | Production ready |
| 90-94 | Good | Minor refinements needed |
| 85-89 | Acceptable | Significant improvement needed |
| <85 | Poor | Redesign patterns / approach |

---

## Validation Datasets

### Training Set (Pattern Development)

- **Size**: 7,000 records (70% of 2004 data)
- **Use**: Pattern creation and refinement
- **No validation**: Not counted in quality metrics

### Validation Set (Quality Measurement)

- **Size**: 1,500 records (15% of 2004 data)
- **Use**: Measure accuracy after pattern tuning
- **Completely held out**: Never used for pattern development

### Test Set (Final Evaluation)

- **Size**: 1,500 records (15% of 2004 data)
- **Use**: Final quality measurement before production
- **Completely held out**: Never used for any development

---

## Success Criteria

### Phase 5 Gates (Extraction Pass/Fail)

**MUST PASS** all of these to proceed to Phase 6:

1. ✅ **Overall Precision ≥ 95%**
2. ✅ **Overall Recall ≥ 90%**
3. ✅ **Overall F1-Score ≥ 92%**
4. ✅ **False Positive Rate ≤ 3%**
5. ✅ **Field Completeness ≥ 95%**
6. ✅ **All Critical Fields** (name, form, capital) meet targets
7. ✅ **Confidence Calibration**: Within 5% of actual accuracy
8. ✅ **Consistency**: All legal forms within 5% of overall

### Production SLA (Ongoing)

Once in production, maintain:

- **Daily Accuracy**: >93% (allows target to slip <2%)
- **Monthly Accuracy**: >95% (must return to target)
- **Uptime**: 99.9% (should process automatically)
- **Latency**: <2 seconds per record (batch processing)
- **False Positives**: <3% (continuous monitoring)

---

## Quality Issues & Resolution

### Issue: High False Positive Rate (>3%)

**Symptoms**: Incorrect data appearing in output

**Root Causes** (in order of likelihood):
1. Regex pattern too permissive (matching non-company data)
2. OCR noise creating false matches
3. Field ambiguity (can't distinguish similar fields)

**Investigation**:
1. Run error analysis: categorize false positives by type
2. Sample false positives: analyze patterns
3. Tighten regex or add negative lookahead

**Resolution Timeline**: 1-2 weeks pattern refinement

---

### Issue: Low Recall (<90%)

**Symptoms**: Missing valid extracted data

**Root Causes**:
1. Regex pattern too strict (not matching valid variants)
2. Field located in unexpected position
3. OCR corruption preventing pattern match
4. NLP fallback not triggered

**Investigation**:
1. Analyze false negatives: what did we miss?
2. Check if pattern variants cover all forms
3. Check spatial location of field in documents

**Resolution Timeline**: 1-3 weeks pattern expansion + testing

---

### Issue: Confidence Score Miscalibration

**Symptoms**: High-confidence records turn out wrong; low-confidence records correct

**Investigation**:
1. Compare stated confidence vs. actual accuracy bins
2. Identify which fields are over/under-confident
3. Retrain confidence scoring model

**Resolution Timeline**: 3-5 days confidence adjustment

---

## Reporting

### Daily Report

```
Extraction Run Summary
Date: 2024-01-20
Records Processed: 10,000
Quality Score: 94.2/100

Critical Metrics:
- Precision: 96.1%
- Recall: 91.3%
- F1-Score: 93.6%
- False Positives: 2.1%
- Field Completeness: 96.8%

By Field:
- Company Name: 99.2% (excellent)
- Capital: 97.1% (excellent)
- Legal Form: 98.9% (excellent)
- Address: 87.4% (acceptable)
- Management: 89.3% (acceptable)

Alerts: None
Status: ✅ PASS (meets daily target >93%)
```

### Monthly Report

```
Monthly Quality Assessment
Month: January 2024
Total Processed: 100,000 records (10 daily runs)

Overall Quality Score: 93.8/100
Status: ✅ MEETING TARGETS

Precision Trend:     93.2% → 94.1% → 95.3% (improving)
Recall Trend:        89.0% → 90.8% → 91.6% (improving)
Uptime:             99.97% (exceeds 99.9% SLA)

Recommendations:
- Address field extraction needs improvement (87%)
- Management extraction doing well; consider expanding
- Two pattern refinements recommended

Next Period Actions:
- [List specific improvements]
```

---

## Quality Improvement Process

### Weekly Review (During Active Development)

1. **Analyze errors** from past week's extraction
2. **Categorize failures**: false positives, false negatives, edge cases
3. **Prioritize fixes**: highest impact first
4. **Update patterns**: refine regex or add new variants
5. **Test**: validate on validation set
6. **Deploy**: if improvement >1% overall; else defer

### Monthly Review (Ongoing Operations)

1. **Trend analysis**: Is quality improving or degrading?
2. **Outlier detection**: Are recent extractions anomalous?
3. **Stakeholder feedback**: Are users finding issues?
4. **Maintenance**: Schedule pattern refinements for next quarter
5. **Documentation**: Update pattern library with insights

---

## Related Documents

- [Validation Results](./VALIDATION_RESULTS.md) - Friend dataset findings
- [Error Analysis](./ERROR_ANALYSIS.md) - Failure mode categorization
- [Extraction Architecture](../4_Modeling/EXTRACTION_ARCHITECTURE.md) - How extraction works

---

**Version**: 1.0 | **Last Updated**: 2024
