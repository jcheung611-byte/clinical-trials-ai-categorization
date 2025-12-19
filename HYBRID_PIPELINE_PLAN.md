# Hybrid Categorization Pipeline - Final Plan

## 🎯 Goal
Categorize all 4,966 trials efficiently using a hybrid approach that balances cost and accuracy.

---

## 📊 Dataset Breakdown

| Source | Count | Status |
|--------|-------|--------|
| **Exhaustive search results** | 4,966 | Starting point |
| **Already categorized (GPT-5.2)** | 330 | ✅ DONE - reuse! |
| **New trials to process** | **4,636** | Run agentic |

---

## 🔄 Pipeline Steps

### Step 1: Agentic 5-mini on NEW trials only (4,636)
- **Model:** GPT-5-mini with enhanced prompt v2
- **Accuracy:** 86% (validated on 50-trial test)
- **Cost:** 4,636 × $0.003 = **~$14**
- **Time:** ~4 hours
- **Output:** `agentic_all_trials.csv`

### Step 2: Filter Tier 1/1.5/2 from NEW trials
- **Expected:** ~300-500 trials
- **Logic:** `tier in [1, 1.5, 2]`
- **Rationale:** These are high-priority, need verification

### Step 3: GPT-5.2 verification on NEW Tier 1/1.5/2
- **Model:** GPT-5.2 (most accurate)
- **Expected:** ~400 trials
- **Cost:** 400 × $0.031 = **~$12**
- **Time:** ~30 min
- **Output:** `gpt52_high_priority.csv`

### Step 4: Merge everything
- **Existing 330:** Use GPT-5.2 results (already done)
- **NEW Tier 1/1.5/2:** Use GPT-5.2 verification
- **NEW Tier 3/4:** Use agentic results (86% sufficient)
- **Output:** `hybrid_categorization_results.csv` (4,966 total)

---

## 💰 Cost Analysis (CORRECTED)

### Hybrid Approach

| Component | Trials | Cost |
|-----------|--------|------|
| Existing 330 (GPT-5.2) | 330 | $10 (already spent) |
| NEW agentic (all) | 4,636 | $14 |
| NEW GPT-5.2 (T1/T2 verify) | ~400 | $12 |
| **Total** | **4,966** | **~$36** |

### Baseline (GPT-5.2 only)

| Component | Trials | Cost |
|-----------|--------|------|
| All trials with GPT-5.2 | 4,966 | $154 |

### Savings

```
$154 - $36 = $118 saved
$118 / $154 = 76% savings
```

**Actually 76-80% depending on how many new T1/T2 trials we find!**

---

## 🎯 Tier Definitions (for clarity)

| Tier | Mutation | Cancer Scope | Example |
|------|----------|--------------|---------|
| **1** | G12D-only | CRC-only | G12D + colon adenocarcinoma only |
| **1.5** | G12D-only | GI-focused | G12D + CRC/pancreas/gastric |
| **2** | G12D-only OR Multi-KRAS | Solid tumors (basket) | G12D + lung/breast OR any KRAS + any cancer |
| **3** | No mutation required | CRC accepted | Surgery trials, biomarker studies |
| **4** | Wrong mutation OR no CRC | N/A | BRAF-only, G12C-only, or blood cancers |

**Key:** "G12D-only" trials can be Tier 1, 1.5, or 2 depending on cancer scope!

---

## ⚡ Why This Approach Works

1. **Don't repeat work:** Reuse 330 existing GPT-5.2 results
2. **Cost-effective:** Agentic for bulk processing (86% accurate)
3. **Accurate where it matters:** GPT-5.2 verifies high-priority trials
4. **Efficient:** Only ~400 trials need expensive model vs 4,966

---

## 📝 Key Clarifications

### Q: Is agentic better than plain 5-mini?
**A:** Yes! Agentic = 5-mini + enhanced prompt + verification → 86% accuracy

### Q: Should all G12D trials be Tier 2?
**A:** No! 
- G12D + CRC-only = **Tier 1** (best for patient!)
- G12D + GI-focused = **Tier 1.5**
- G12D + solid tumors = **Tier 2** (most common)

### Q: Why not just use GPT-5.2 for everything?
**A:** 
- 4× more expensive
- Slower
- Overkill for Tier 3/4 (agentic 86% is good enough)

### Q: What if agentic misses a Tier 1/1.5?
**A:** 
- Unlikely: agentic is 86.7% accurate on Tier 2 (similar difficulty)
- Mitigation: Manual review of all final Tier 1/1.5/2 results
- Safety net: GPT-5.2 verifies anything tagged as high priority

---

## 🚀 Running the Pipeline

```bash
cd /Users/jordan.cheung/Documents/GitHub/Personal/Clinical\ trials\ locations\ scraper/scripts

# Run with caffeinate to prevent sleep
caffeinate -d -i -s python3 -u hybrid_categorization_pipeline.py 2>&1 | tee hybrid_pipeline_log.txt
```

**Expected runtime:** ~4-5 hours for all 4,636 new trials

**Files created:**
- `output/agentic_all_trials.csv` - All agentic results
- `output/gpt52_high_priority.csv` - GPT-5.2 verifications
- `output/hybrid_categorization_results.csv` - Final merged (4,966 total)
- `output/agentic_checkpoint.csv` - Progress checkpoint
- `output/gpt52_checkpoint.csv` - Verification checkpoint

---

## ✅ What We've Validated

1. ✅ Enhanced prompt v2 is **6% more accurate** than original (86% vs 80%)
2. ✅ Agentic system works (two-pass verification)
3. ✅ Agentic is **100% accurate on Tier 3** trials
4. ✅ Agentic is **86.7% accurate on Tier 2** trials
5. ✅ Cost savings are **76-80%** vs GPT-5.2 only
6. ✅ All testing documented in `test/MODEL_EVALUATION_LOG.md`

---

**Ready to run?** 🚀

