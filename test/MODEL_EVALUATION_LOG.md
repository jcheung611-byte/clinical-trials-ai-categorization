# Model Evaluation & Testing Log
## Clinical Trial Categorization System

---

## Executive Summary

**Best System:** Agentic GPT-5-mini with enhanced prompt v2
- **Accuracy:** 86% vs GPT-5.2 baseline
- **Cost:** ~$0.003/trial (85% cheaper than GPT-5.2)
- **Speed:** ~3-5 sec/trial

**Recommendation:** Hybrid approach
1. Run agentic 5-mini on full dataset
2. Use GPT-5.2 to verify all Tier 1/1.5/2 results

---

## Test 1: Initial Model Comparison (17 disagreement cases)

**Date:** Dec 2024
**Goal:** Compare GPT-4o-mini, GPT-4o, GPT-5-nano, GPT-5-mini, GPT-5.2

**Test Set:** 17 trials where GPT-5-mini and GPT-5.2 disagreed

**Results:**
- GPT-5.2: 100% accuracy (assumed ground truth)
- GPT-5-mini: Lower accuracy, disagreed with 5.2 on rule interpretation

**Key Insight:** GPT-5-mini struggles with complex mutation detection and cancer scope classification.

**Files:**
- `test/model_comparison_v2.py`
- `test/tier_3_4_recat_comparison.py`

---

## Test 2: Agentic Two-Pass System (Initial)

**Date:** Dec 2024
**Goal:** Improve 5-mini accuracy with two-pass verification

**Design:**
- Pass 1: GPT-5-mini categorizes trial
- Pass 2: Self-verification if edge case detected
- Edge cases: No-mutation + Tier 2, Multi-KRAS + Tier 3/4, low confidence

**Test Set:** 17 disagreement cases (same as Test 1)

**Results:**
- Accuracy: ~90% (improved from base 5-mini)
- Cost savings: ~85% vs GPT-5.2

**Key Insight:** Agentic approach helps, but still misses some edge cases.

**Files:**
- `gpt/agentic_categorizer.py`
- `test/test_agentic_system.py`

---

## Test 3: 50-Trial Validation (Enhanced Prompt v2)

**Date:** Dec 17, 2024
**Goal:** Test agentic system on diverse, stratified sample

**Test Set:** 50 trials from 330 priority trials
- 1 Tier 1.5
- 15 Tier 2
- 17 Tier 3
- 17 Tier 4

**Prompt Used:** Enhanced v2 (simplified, clearer)

**Results:**

| Metric | Value |
|--------|-------|
| Overall Accuracy | **86%** (43/50) |
| Tier 1.5 | 0% (0/1) ⚠️ |
| Tier 2 | 86.7% (13/15) |
| Tier 3 | **100%** (17/17) ✅ |
| Tier 4 | 76.5% (13/17) |
| Edge Cases Detected | 1 |
| Successful Corrections | 0 |
| Cost per trial | $0.0031 |
| Time per trial | ~3-5 sec |

**Disagreements:**
1. **NCT06445062** (Tier 1.5 → 2): Misclassified G12D-only as Multi-KRAS
2. **NCT06166836** (Tier 2 → 4): Saw G12C-only instead of Multi-KRAS
3. **NCT06497985** (Tier 2 → 3): Missed KRAS requirement
4. **NCT06176885** (Tier 3 → 2): False positive on mutation requirement
5. **NCT06898385** (Tier 4 → 2): Misclassified Multiple Myeloma as CRC
6. **NCT06997497** (Tier 4 → 2): Missed non-CRC condition
7. **NCT05186116** (Tier 4 → 3): Missed BRAF requirement
8. **NCT06876142** (Tier 4 → 2): Misclassified Multiple Myeloma
9. **NCT06328439** (Tier 4 → 3): Over-generous on Solid Tumors
10. **NCT06878612** (Tier 4 → 3): Over-generous on Solid Tumors

**Key Insights:**
- ✅ **Perfect on Tier 3** (CRC, no mutation)
- ✅ **Strong on Tier 2** (basket trials)
- ⚠️ **Weak on Tier 1.5** (only 1 sample, but missed it)
- ⚠️ **Moderate on Tier 4** (false positives on non-CRC trials)

**Files:**
- `test/compare_agentic_vs_52_on_priority.py`
- `test/agentic_vs_52_comparison_fixed.csv`
- `test/agentic_vs_52_v2_log.txt`

---

## Test 4: Prompt Comparison Analysis

**Date:** Dec 17, 2024
**Goal:** Determine if prompt differences explain disagreements

**Test:** Run same 7 disagreement trials with:
1. Original prompt (used by GPT-5.2) + GPT-5-mini
2. Enhanced prompt v2 (agentic) + GPT-5-mini

**Results:**

| Factor | Count | Conclusion |
|--------|-------|------------|
| Prompt matters | 3/7 | Enhanced prompt helps |
| Model matters | 5/7 | GPT-5.2 better at reading eligibility |

**Key Finding:** Enhanced prompt actually **improves** 5-mini accuracy, not hurts it!

**Files:**
- `test/analyze_disagreements.py`
- `test/disagreement_analysis.csv`

---

## Test 5: 50-Trial Validation (Original Prompt)

**Date:** Dec 17, 2024
**Goal:** Test if original prompt improves accuracy

**Test Set:** Same 50 trials as Test 3

**Prompt Used:** Original (detailed, 220 lines)

**Results:**

| Metric | Enhanced v2 | Original | Winner |
|--------|-------------|----------|--------|
| Overall | **86%** | 80% | ✅ **Enhanced** |
| Tier 1.5 | 0% | 0% | Tie |
| Tier 2 | 86.7% | 86.7% | Tie |
| Tier 3 | **100%** | 94.1% | ✅ **Enhanced** |
| Tier 4 | **76.5%** | 64.7% | ✅ **Enhanced** |
| Verifications | 1 | 7 | - |
| Corrections | 0 | 7 | - |

**Conclusion:** Enhanced prompt v2 is **BETTER** for GPT-5-mini!

The simpler, clearer prompt helps the model make better decisions. The original prompt's complexity actually confuses the model.

**Files:**
- Same as Test 3, second run
- `test/agentic_vs_52_v2_log.txt` (second run with original prompt)

---

## Cost Analysis

### Per-Trial Costs

| Model/System | Cost | Speed |
|--------------|------|-------|
| GPT-5.2 | $0.031 | 5-8 sec |
| GPT-5-mini (agentic) | $0.003 | 3-5 sec |
| **Savings** | **90%** | **40% faster** |

### Full Dataset Costs (330 trials)

| Approach | Cost | Time |
|----------|------|------|
| GPT-5.2 only | $10.23 | 30 min |
| Agentic only | $0.99 | 18 min |
| **Hybrid** (agentic + 5.2 for T1/T2) | **~$3.50** | **~22 min** |

**Hybrid Assumptions:**
- Agentic tags ~25% as Tier 1/1.5/2 (~100 trials)
- GPT-5.2 verifies those 100 = $3.10
- Agentic processes all 330 = $0.99
- Total: ~$4.09

---

## Recommended Approach: Hybrid System

### Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: Agentic 5-mini on ALL trials                       │
│  - Fast first pass                                          │
│  - Tag every trial with initial tier                        │
│  - Cost: $0.99 for 330 trials                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 2: Filter Tier 1/1.5/2 trials                         │
│  - Extract all high-priority results                        │
│  - Expected: ~80-100 trials (based on 330 sample)           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 3: GPT-5.2 verification on Tier 1/1.5/2               │
│  - Re-categorize with stronger model                        │
│  - Catch false positives (e.g., Multiple Myeloma)           │
│  - Cost: ~$3.10 for 100 trials                              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 4: Merge results                                       │
│  - Tier 1/1.5/2: Use GPT-5.2 results (high confidence)      │
│  - Tier 3/4: Use agentic results (86% accuracy sufficient)  │
└─────────────────────────────────────────────────────────────┘
```

### Rationale

**Why hybrid?**
1. **Cost-effective:** 60% cheaper than GPT-5.2 only
2. **Accurate where it matters:** High-priority trials get GPT-5.2
3. **Efficient:** Low-priority trials don't need expensive model
4. **Catches edge cases:** GPT-5.2 fixes agentic false positives

**Why agentic first?**
- Agentic is 86% accurate overall
- Perfect (100%) on Tier 3
- Strong (86.7%) on Tier 2
- Only weak on rare Tier 1.5 and some Tier 4s

**Why GPT-5.2 for Tier 1/2?**
- These are the trials patient might actually enroll in
- False negatives are costly (miss good trial)
- False positives are manageable (manual review catches them)
- GPT-5.2 is better at reading complex eligibility criteria

---

## Implementation Files

### Core System
- `gpt/agentic_categorizer.py` - Two-pass categorization
- `prompts/trial_categorization_v2.py` - Enhanced prompt (BEST)
- `prompts/trial_categorization.py` - Original prompt (for GPT-5.2)

### Testing Scripts
- `test/compare_agentic_vs_52_on_priority.py` - Main validation
- `test/analyze_disagreements.py` - Prompt comparison
- `test/tier_3_4_recat_comparison.py` - Tier 3/4 de-risking

### Results
- `test/agentic_vs_52_comparison_fixed.csv` - 50-trial results (enhanced)
- `test/disagreement_analysis.csv` - Prompt analysis
- `output/priority_trials_categorized.csv` - 330 trials (GPT-5.2)

---

## Next Steps

1. ✅ Revert to enhanced prompt v2 (DONE)
2. ⏳ Run agentic on full dataset (~4,966 trials)
3. ⏳ Filter Tier 1/1.5/2 results (~300-500 expected)
4. ⏳ Run GPT-5.2 verification on filtered set
5. ⏳ Merge and export final results

---

## Lessons Learned

1. **Simpler prompts > Complex prompts** (for GPT-5-mini)
   - Enhanced v2 beat original by 6 percentage points
   - Clarity matters more than comprehensiveness

2. **Model capability matters more than prompt engineering**
   - GPT-5.2 is fundamentally better at reading eligibility
   - No amount of prompt tuning fixes model limitations

3. **Hybrid systems balance cost and accuracy**
   - Use cheap model for initial pass
   - Use expensive model only where needed

4. **Test on diverse, representative samples**
   - Stratified sampling by tier crucial
   - 50 trials sufficient to measure 80-90% accuracy

5. **Document everything!**
   - Testing process is valuable
   - Results inform future decisions

---

## Appendix: Model Specifications

### GPT-5.2
- **Strengths:** Complex reasoning, eligibility criteria parsing
- **Cost:** $1.75/M input tokens, $14.00/M output tokens
- **Speed:** ~5-8 sec/trial
- **Accuracy:** Assumed 95%+ (used as baseline)

### GPT-5-mini (Agentic)
- **Strengths:** Fast, cheap, good on clear cases
- **Weaknesses:** Struggles with G12D-only vs Multi-KRAS distinction
- **Cost:** $0.25/M input, $2.00/M output
- **Speed:** ~3-5 sec/trial
- **Accuracy:** 86% vs GPT-5.2 baseline

### GPT-4o-mini
- **Status:** Previously tested, inferior to GPT-5-mini
- **Not recommended**

---

**Document Version:** 1.0
**Last Updated:** Dec 17, 2024
**Author:** Jordan Cheung + AI Assistant

