# WORK PLAN - JORT Constitution Notice Extraction Pipeline

**Project:** Infyntra - De l'opacité documentaire à l'intelligence économique  
**Phase:** JORT Constitution Pipeline Implementation  
**Duration:** [Project Start] - Ongoing  
**Status:** Core Pipeline + Search/BI Delivered, Data Quality Hardening In Progress  
**Last Updated:** April 9, 2026

---

## Project Summary

### **Objective**
Develop an automated extraction pipeline to transform **unstructured Tunisian legal notices (JORT)** into **structured economic intelligence data**.

Target: Constitution announcements from the Journal Officiel de la République Tunisienne (JORT), focusing on 2004 data as proof-of-concept.

### **Problem Addressed**
- ❌ JORT publishes 1000+ daily legal announcements in non-indexed PDFs
- ❌ No automated way to extract company formation data (name, capital, managers, etc.)
- ✅ Our solution: Hybrid regex + NLP pipeline for intelligent extraction

### **Deliverables**
1. Extraction pipeline (6 modules)
2. Analysis tools (validation vs. reference data)
3. Event layer + company timelines (multi-year)
4. Search API (FastAPI + Elasticsearch)
5. BI dashboards (Executive + Company 360)
6. Documentation (11-part technical guide)
7. Output datasets (raw + cleaned post-OCR JSON)

---

## Current Validated State (April 2026)

Latest large-scale run (`end2end/run_end2end_direct.py`):

- PDFs processed: 1568
- Notices processed: 250008
- Events generated: 249927
- Constitution records: 67932
- Errors: 0
- Tax IDs extracted/valid: 58907 / 58907
- Events with activity taxonomy category: 50314
- Events with parse confidence score: 206045
- Events with manager populated: 69374

Post-OCR quality regulation (`end2end/run_after_ocr.py`) now produces:

- suspicious `company_id` flagging (`__suspicious__`)
- normalized `company_id` formatting
- before/after quality report
- top suspicious company ID leaderboard
- latest suspicious metrics: 1386 instances, 106 unique values

---

## Timeline & Milestones

### **PHASE 1: Pipeline Core Development** ✅ COMPLETE

| Week | Task | Status | Owner |
|------|------|--------|-------|
| 1-2 | Architecture design, module scaffolding | ✅ | Iyed |
| 2-3 | Text cleaning + pattern library | ✅ | Iyed |
| 3-4 | Constitution parser + form-aware logic | ✅ | Iyed |
| 4-5 | NLP enrichment (spaCy integration) | ✅ | Iyed |
| 5-6 | Friend enrichment + validation | ✅ | Iyed |
| 6 | Testing + documentation | ✅ | Iyed |
| 7 | Performance optimization | ✅ | Iyed |

**Duration:** 7 weeks  
**Status:** ✅ Complete

---

### **PHASE 2: Refinement & Scaling** 🔄 IN PROGRESS

| Week | Task | Effort | Status |
|------|------|--------|--------|
| 7-8 | Precision tuning (reduce false positives) | 40h | 🔄 In Progress |
| 8-9 | Additional test coverage (unit + integration) | 30h | 📋 Planned |
| 9-10 | Performance optimization (multithreading) | 40h | 📋 Planned |
| 10-11 | Evaluation metrics + formal accuracy assessment | 20h | 📋 Planned |
| 11-12 | Documentation finalization | 20h | 📋 Planned |

**Estimated Duration:** 6 weeks  
**Status:** 🔄 60% complete (2 weeks elapsed)

---

### **PHASE 3: Coverage Expansion** 📋 PLANNED

| Week | Task | Effort | Status |
|------|------|--------|--------|
| 13-15 | Extend to modification notices | 60h | 📋 Not Started |
| 15-17 | Extend to liquidation notices | 50h | 📋 Not Started |
| 17-18 | Handle 2005-2006 data (generalization testing) | 40h | 📋 Not Started |
| 18-20 | Cross-year evaluation | 30h | 📋 Not Started |

**Estimated Duration:** 8 weeks  
**Status:** 📋 Not started (planned after Phase 2)

---

### **PHASE 4: Production & Deployment** 🔄 PARTIALLY COMPLETED

| Week | Task | Effort | Status |
|------|------|--------|--------|
| 20-22 | API development (FastAPI/Elasticsearch wrapper) | 60h | ✅ Completed |
| 22-23 | BI dashboards (Executive + Company 360) | 30h | ✅ Completed |
| 23-24 | Production deployment (containerization + ops hardening) | 40h | 📋 Not Started |
| 24-25 | Real-time JORT feed integration + user training | 25h | 📋 Not Started |

**Estimated Duration:** 6 weeks  
**Status:** 🔄 API/BI completed, deployment and feed integration pending

---

## Revised Immediate Priorities

1. Reduce `__unknown_company__` rate on modification/liquidation events.
2. Improve company identity resolution beyond tax ID-only matches.
3. Calibrate taxonomy category confidence thresholds and validate category drift.
4. Add automated quality gates for suspicious `company_id` and event-level regressions.
5. Consolidate KPI monitoring from extraction outputs into BI dashboards.

---

## Work Breakdown Structure (WBS)

### **1. Core Pipeline Components**

#### **1.1 Text Normalization** ✅
- Module: `extractor/cleaner.py`
- Effort: 2 days
- Status: ✅ Complete
- Deliverable: clean_text() function

#### **1.2 Regex Pattern Library** ✅
- Module: `extractor/patterns.py`
- Effort: 5 days
- Status: ✅ Complete
- Deliverable: 12 field patterns, 4 role patterns

#### **1.3 Constitution Parser** ✅
- Module: `extractor/parser.py`
- Effort: 8 days
- Status: ✅ Complete
- Deliverable: parse_notice(), is_constitution_notice()

#### **1.4 NLP Enrichment** ✅
- Module: `extractor/nlp_enrichment.py`
- Effort: 6 days
- Status: ✅ Complete
- Deliverable: spaCy integration, leadership extraction

#### **1.5 Friend Enrichment** ✅
- Module: `extractor/enrichment.py`
- Effort: 4 days
- Status: ✅ Complete
- Deliverable: Reference data validation & fallback

#### **1.6 File Handling** ✅
- Module: `utils/filesystem.py`
- Effort: 2 days
- Status: ✅ Complete
- Deliverable: Path parsing, metadata extraction

#### **1.7 Pipeline Orchestrator** ✅
- Module: `main.py`
- Effort: 3 days
- Status: ✅ Complete
- Deliverable: Entry point, CLI, statistics

**Phase 1 Total:** 30 days = 7.5 weeks (accounting for testing, debugging)

### **2. Analysis & Validation Tools**

#### **2.1 Friend Diff Analysis** ✅
- Module: `analyze_friend_diff.py`
- Effort: 2 days
- Status: ✅ Complete
- Deliverable: Blocker reports, gap analysis

#### **2.2 Evaluation Script** ✅
- Module: `eval.py`
- Effort: 1 day
- Status: ✅ Complete
- Deliverable: Per-form statistics, quality metrics

**Subtotal:** 3 days (included in Phase 1)

### **3. Documentation** 🔄

#### **3.1 Technical Documentation** 🔄
- 11 markdown files covering:
  - Enterprise & context
  - Architecture & design
  - Implementation details
  - Data flow & patterns
  - NLP & enrichment
  - Validation & status
- Effort: 10 days
- Status: 🔄 Complete (draft), in review

#### **3.2 User Documentation** 📋
- CLI usage guide
- Configuration reference
- Common troubleshooting
- Effort: 3 days
- Status: 📋 Planned (Phase 2)

**Subtotal:** 13 days planned

### **4. Testing & Quality** 🔄

#### **4.1 Manual Testing** ✅
- 100+ notice samples validated
- Pattern accuracy verified
- OCR robustness tested
- Effort: 3 days
- Status: ✅ Complete

#### **4.2 Unit Tests** 📋
- Test fixtures for each module
- Coverage target: 80%+
- Effort: 8 days
- Status: 📋 Planned (Phase 2)

#### **4.3 Integration Tests** 📋
- End-to-end pipeline tests
- Reference data validation
- Effort: 5 days
- Status: 📋 Planned (Phase 2)

**Subtotal:** 16 days planned (3 done in Phase 1, 13 planned Phase 2)

### **5. Performance & Optimization** 🔄

#### **5.1 Profiling** 🔄
- Identify bottlenecks
- Current: ~900ms per notice
- Effort: 2 days
- Status: 🔄 30% done

#### **5.2 Multithreading** 📋
- Parallel file processing
- Thread pool management
- Target: 10x speedup
- Effort: 8 days
- Status: 📋 Planned (Phase 2)

#### **5.3 Model Optimization** 📋
- Lazy model loading
- Caching strategy
- Target: <100ms per notice
- Effort: 5 days
- Status: 📋 Planned (Phase 2)

**Subtotal:** 15 days planned

---

## Resource Allocation

### **Team**

| Role | Name | Capacity | Assignment |
|------|------|----------|-----------|
| Developer | Mohamed Iyed TAHRI | 80% | Pipeline development, architecture, testing |
| Tutor/Advisor | Chaima KADDOUR | 20% | Design review, acceptance criteria |

**Total Team Effort:** 1 FTE developer equivalent

### **External Resources**

| Resource | Purpose | Cost | Status |
|----------|---------|------|--------|
| spaCy French Model | NLP enrichment | Free | ✅ Integrated |
| Tesseract OCR | Future OCR phase | Free | 📋 Not yet used |
| GitLab/GitHub | Version control | Free | ✅ Using |
| Development Environment | VS Code, Python | Free | ✅ Using |

---

## Dependencies & Constraints

### **Technical Dependencies**

| Dependency | Version | Status | Impact |
|------------|---------|--------|--------|
| Python | 3.9+ | ✅ Available | Core language |
| spaCy | 3.0+ | ✅ Installed | NLP fallback |
| spacy fr_core_news_sm | Latest | ✅ Installed | French NER/tokenization |
| Tesseract | 4.0+ | 📋 Not required yet | Future OCR phase |
| JORT Dataset | 2004 anonyme | ✅ Available | Test data (5000 notices) |
| Friend Reference Data | 2004 anonyme | ✅ Available | Validation data (1000 refs) |

### **Constraints**

| Constraint | Impact | Mitigation |
|-----------|--------|-----------|
| OCR quality variable (old scans) | Pattern matching challenges | Add NLP fallback, reference validation |
| Multi-encoding files (UTF-8, CP1252, Latin-1) | Decoding errors | Cascade encoding fallback |
| Limited Friend coverage (1000 for 5000 notices) | Sparse reference data | Use as validation only, not primary |
| Performance (single-threaded ~1s per notice) | Scaling to 200k notices = hours | Multithreading for Phase 3 |
| SUARL format variability (37% coverage) | Lower recall for rare forms | Focus improvements on common forms first |

---

## Success Criteria & Acceptance

### **Extraction Quality**

**Phase 1 Acceptance (✅ MET):**
- Overall accuracy: ≥85% → Achieved 90%
- Company name extraction: ≥80% → Achieved 95%
- No critical bugs in parser → ✅ Verified
- Handles all 4 legal forms → ✅ Verified

**Phase 2 Target:**
- Overall accuracy: ≥90% (currently 90%)
- Field-specific precision: ≥90% for top 3 fields
- Reduce false positives in leadership: ≤5% noise

**Phase 3 Target:**
- Accuracy maintained across 2004-2006 → Benchmark: ≥88%
- Coverage expansion: Modifications + Liquidations at ≥80%

### **Performance**

**Phase 1 Acceptance (✅ MET):**
- Process 5000 notices in <2 hours → Achieved (~45min)
- Memory footprint: <300MB → Achieved 200MB

**Phase 2 Target:**
- Process 5000 notices in <5 minutes (10x improvement)
- Single-notice latency: <100ms

**Phase 3 Target:**
- Process 200k notices (2004-2025) in <1 hour

### **Documentation**

**Phase 1 Acceptance (✅ MET):**
- Architecture documented → ✅ 11 markdown files
- Code commented → ✅ Each module has docstrings
- Example usage → ✅ main.py with argparse

**Phase 2 Target:**
- User guide + troubleshooting
- API documentation (if API created)

---

## Risk Management

### **Identified Risks**

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| **Precision degradation on newer data (2005+)** | Medium | High | Early testing on 2005 sample |
| **NLP model size/loading time** | High | Medium | Lazy loading, model caching |
| **Encoding detection fails on edge PDFs** | Low | High | Fallback to charset detection lib |
| **SUARL format too variable** | Medium | Medium | Accept lower coverage, document |
| **Friend data doesn't generalize to 2005+** | High | Low | Use Friend 2004-only, not for newer years |

### **Contingency Plans**

1. **If NLP too slow:** Make NLP optional, provide flag for regex-only mode
2. **If SUARL coverage insufficient:** Expert review + manual pattern tuning (2 days)
3. **If new data type incompatible:** Extend parser to handle new fields (3-5 days)
4. **If performance bottleneck:** Switch to multithreading immediately (Phase 2)

---

## Communication & Reporting

### **Status Updates**

**Frequency:** Weekly  
**Format:** Email + platform submission

**Content:**
- Completed tasks (this week)
- Blockers/Issues
- Metrics update (extraction quality, performance)
- Next week plan

### **Presentation Schedule**

- **Week of March 31:** Submit plan + draft documentation → ✅ THIS WEEK
- **Week of April 7:** Internal review with tutor
- **Week of April 14:** Final presentation (slides + demo)
- **Post-presentation:** Phase 2 refinement based on feedback

### **Documentation Location**

```
/home/iyedpc1/jort/
├── docs/
│   ├── 1_ENTREPRISE.md
│   ├── 2_CONTEXTE_PROBLEMATIQUE.md
│   ├── 3_ETUDE_EXISTANT.md
│   ├── 4_SOLUTION_CONCEPTION.md
│   ├── 5_ANALYSE_BESOIN_TECH.md
│   ├── 6_METHODOLOGIE_IMPLEMENTATION.md
│   ├── 7_EXTRACTION_PIPELINE.md
│   ├── 8_PATTERN_EXTRACTION.md
│   ├── 9_GOVERNANCE_NLP.md
│   ├── 10_ENRICHMENT_VALIDATION.md
│   └── 11_ETAT_AVANCEMENT.md
├── WORK_PLAN.md ← This file
└── [source code in ./]
```

---

## Budget & Effort Summary

### **Effort Allocation**

| Phase | Duration | Effort | Status |
|-------|----------|--------|--------|
| Phase 1: Core Pipeline | 7 weeks | 280 hours | ✅ Complete |
| Phase 2: Refinement | 6 weeks | 150 hours | 🔄 70% planned |
| Phase 3: Scaling | 8 weeks | 180 hours | 📋 Not started |
| Phase 4: Production | 6 weeks | 155 hours | 📋 Not started |
| **TOTAL** | **27 weeks** | **765 hours** | **35% complete** |

### **Cost (Internship hours @ 0 cost)**

- Developer: 1 FTE = 27 weeks
- Infrastructure: Free (local machine, free tools)
- **Total Project Cost:** Internship time only

---

## Appendix: Running the Pipeline

### **Setup (One-time)**

```bash
# Clone/navigate to project
cd /home/iyedpc1/jort
source .venv/bin/activate

# Install dependencies (if needed)
pip install -r requirements.txt

# Download spaCy model (if not already installed)
python -m spacy download fr_core_news_sm
```

### **Basic Execution**

```bash
# Process 2004 anonyme data with Friend enrichment
python main.py \
  --dataset constitution \
  --output output/ \
  --friend-data constitution/anonyme/2004

# Output files:
# - output/extracted_notices.json (main results)
# - output/friend_2004_side_by_side_diff.json (validation report)
```

### **Analysis**

```bash
# Generate blocker reports
python analyze_friend_diff.py constitution/anonyme/2004 output/

# Evaluate extraction quality (statistics)
python eval.py output/extracted_notices.json
```

---

## References

### **Project Documents**
- Infyntra System Presentation (company provided)
- JORT Official Database (journal.tn)
- This techical documentation (11 files in ./docs/)

### **Technical References**
- spaCy Documentation: https://spacy.io/
- Python Regex: https://docs.python.org/3/library/re.html
- JSON Schema: https://json-schema.org/

### **Data Sources**
- JORT 2004 Constitution Notices: constitution/anonyme/2004/
- Friend Reference Data: constitution/anonyme/2004/*.json (1000 files)

---

## Sign-Off

**Prepared by:** Mohamed Iyed TAHRI  
**Date:** March 31, 2026  
**Status:** Phase 1 Complete, Phase 2 In Progress  
**Next Review:** April 7, 2026

**Tutor Approval:**  
[ ] Chaima KADDOUR - Reviewed and Accepted

---

**END OF WORK PLAN**

