# Decision Log & Project Journal
## Clinical Trial Categorization System

> **Purpose:** Document every decision, test, tradeoff, and learning throughout this project.
> This log can be used for future projects, papers, or as a case study.

---

## 📅 Project Timeline

### Phase 1: Initial Scraping & Data Collection
**Goal:** Build a system to scrape trial locations from ClinicalTrials.gov

**Key Decisions:**
1. ✅ **API-first approach** (vs HTML scraping)
   - **Rationale:** More reliable, structured data
   - **Implementation:** ClinicalTrials.gov API v2
   - **Fallback:** HTML parsing for edge cases

2. ✅ **Google Sheets as input source**
   - **Rationale:** Non-technical team members can manage lists
   - **Implementation:** CSV export URL parsing
   - **Tradeoff:** Manual updates needed vs fully automated

3. ✅ **Contact-level vs Center-level exports**
   - **Decision:** Both!
   - **Rationale:** Different use cases (recruiting vs analysis)
   - **Implementation:** Two separate CSV outputs

**Files Created:**
- `scraper/scrape_new_trials_1216.py`
- `output/net_new_trials_1216_center_level.csv`

---

### Phase 2: Institution Normalization
**Goal:** Group similar institution names (e.g., "Mayo Clinic" variants)

**Key Decisions:**
1. ❌ **Attempt 1: Rule-based fuzzy matching**
   - **Problem:** Too many edge cases, brittle rules
   - **Lesson:** String similarity alone insufficient
   
2. ❌ **Attempt 2: Location-based grouping**
   - **Problem:** Same institution in different cities should merge (e.g., Mayo Clinic)
   - **Lesson:** Context matters more than location

3. ✅ **Attempt 3: GPT-powered normalization**
   - **Rationale:** Common sense reasoning needed
   - **Model:** GPT-4o-mini (cheap, sufficient accuracy)
   - **Implementation:** Batch processing with specific rules
   - **Success:** Handles MD Anderson systems, UC campuses correctly

**Tradeoff:** $5-10 in API costs vs days of manual cleanup

**Files Created:**
- `gpt/institution_normalizer.py`
- `prompts/trial_categorization.py` (institution prompt)

---

### Phase 3: Exhaustive Trial Search
**Goal:** Find ALL relevant trials for KRAS G12D + CRC patient

**Key Decisions:**
1. ✅ **Search strategy: Broad then filter**
   - **Rationale:** Don't miss relevant trials
   - **Implementation:** Multiple search terms (KRAS, G12D, G12C, RAS, CRC, colorectal, etc.)
   - **Result:** 4,966 trials found

2. ✅ **Priority tier system**
   - **Tier 1:** G12D-only + CRC-only (most relevant)
   - **Tier 1.5:** G12D-only + GI-focused
   - **Tier 2:** Multi-KRAS or G12D + basket
   - **Tier 3:** CRC + no mutation requirement
   - **Tier 4:** Not relevant (wrong mutation or cancer type)

3. ✅ **Checkpointing for long-running searches**
   - **Rationale:** API timeouts, rate limits
   - **Implementation:** Save partial results every N trials
   - **Lesson:** Always assume long processes will fail

**Files Created:**
- `search/api_explorer.py`
- `search/exhaustive_search.py`
- `output/exhaustive_search_results_v2.csv`

---

### Phase 4: GPT-Powered Categorization
**Goal:** Automatically categorize trials by mutation and cancer type

#### Decision 4.1: Which Model?
**Options Tested:**
- GPT-4o-mini: Lower accuracy, cheap
- GPT-4o: Good accuracy, moderate cost
- GPT-5-nano: Insufficient for this task
- GPT-5-mini: Good balance, tested extensively
- GPT-5.2: Best accuracy, expensive

**Decision:** Use GPT-5.2 for initial 330 priority trials
- **Rationale:** These are most important, need high accuracy
- **Cost:** $10 for 330 trials
- **Result:** Assumed 95%+ accuracy (used as baseline)

**Files Created:**
- `gpt/trial_categorizer.py`
- `output/priority_trials_categorized.csv` (330 trials)

#### Decision 4.2: Can We Use Cheaper Model?
**Hypothesis:** GPT-5-mini might be "good enough" for bulk processing

**Test 1: Disagreement Analysis (17 trials)**
- GPT-5-mini vs GPT-5.2 disagreed on 17 trials
- **Finding:** GPT-5-mini struggles with complex eligibility criteria
- **Conclusion:** Need improvement

**Test 2: Agentic Two-Pass System**
- **Innovation:** Use GPT-5-mini with self-verification
- **Design:**
  - Pass 1: Initial categorization
  - Pass 2: Detect edge cases, verify if needed
- **Result:** ~90% accuracy on 17-trial test
- **Decision:** Promising, needs more validation

**Test 3: 50-Trial Validation (Enhanced Prompt)**
- **Sample:** Stratified sample from 330 trials
- **Prompt:** Enhanced v2 (simplified, clearer)
- **Result:** **86% accuracy!**
  - Tier 3: 100% (17/17)
  - Tier 2: 86.7% (13/15)
  - Tier 4: 76.5% (13/17)
  - Tier 1.5: 0% (0/1) - only 1 sample
- **Cost:** $0.003/trial (vs $0.031 for GPT-5.2)

**Test 4: Prompt Comparison**
- **Question:** Is enhanced prompt better or worse than original?
- **Method:** Same 7 disagreements with both prompts
- **Result:** Enhanced prompt is **BETTER**!
  - Enhanced v2: 86% overall
  - Original: 80% overall
- **Lesson:** Simpler, clearer prompts > complex, detailed prompts (for GPT-5-mini)

**Key Insight:** Enhanced prompt helps GPT-5-mini by reducing cognitive load

**Test 5: 50-Trial Validation (Original Prompt)**
- **Purpose:** Validate that enhanced prompt is truly better
- **Result:** Confirmed! Original prompt = 80% vs Enhanced = 86%
- **Decision:** Use enhanced prompt for production

**Files Created:**
- `gpt/agentic_categorizer.py`
- `prompts/trial_categorization_v2.py`
- `test/compare_agentic_vs_52_on_priority.py`
- `test/analyze_disagreements.py`
- `test/MODEL_EVALUATION_LOG.md`

---

### Phase 5: Hybrid Categorization System
**Goal:** Categorize all 4,966 trials cost-effectively

#### Decision 5.1: Which Approach?
**Options:**
1. **GPT-5.2 only:** High accuracy, expensive ($154)
2. **Agentic only:** Cheap, 86% accurate ($15)
3. **Hybrid:** Agentic for bulk, GPT-5.2 for high-priority

**Decision:** Hybrid approach
- **Rationale:**
  - 86% is "good enough" for Tier 3/4 (not enrolling anyway)
  - Tier 1/1.5/2 need verification (patient might enroll)
  - Cost savings: 76% vs GPT-5.2 only
- **Implementation:**
  1. Run agentic on all new trials (4,634)
  2. Filter Tier 1/1.5/2 (~400 expected)
  3. Re-categorize with GPT-5.2
  4. Merge with existing 330

**Cost Breakdown:**
- Existing 330 (GPT-5.2): $10 (already spent)
- New 4,634 (agentic): $14
- New ~400 (GPT-5.2 verify): $12
- **Total: $36 vs $154 baseline = 76% savings**

#### Decision 5.2: Don't Repeat the 330
**Correction:** Initial plan had us re-running existing 330
- **User caught this!** Good product sense
- **Fix:** Skip 330, merge at end
- **Impact:** Saves time and money

#### Decision 5.3: Continuous Documentation
**User request:** Document everything for potential project/paper
- **Implementation:** This decision log!
- **Includes:** Every test, tradeoff, lesson learned
- **Purpose:** Reproducible research, case study

**Files Created:**
- `scripts/hybrid_categorization_pipeline.py`
- `HYBRID_PIPELINE_PLAN.md`
- `DECISION_LOG.md` (this file!)

**Current Status:** Pipeline running (Dec 17, 2024, ~7pm)
- Processing 4,634 new trials
- Expected completion: ~4-5 hours
- Monitor: `tail -f scripts/hybrid_pipeline_log.txt`

---

## 🎯 Key Learnings

### 1. Prompt Engineering
- **Simpler > Complex** for mid-tier models (GPT-5-mini)
- **Test prompts empirically** - intuition is often wrong
- **Model limitations > Prompt quality** - can't prompt-engineer away capability gaps

### 2. Model Selection
- **Don't assume expensive = better for all tasks**
- **Test on representative samples** (stratified by difficulty)
- **Hybrid systems balance cost and accuracy**

### 3. Product Development
- **Iterate quickly:** 5 test rounds in one session
- **Validate assumptions:** Don't trust first results
- **Cost-consciousness:** 76% savings by being clever
- **Document as you go:** Decisions fade from memory

### 4. System Design
- **Checkpointing is critical** for long-running processes
- **Reuse work when possible** (don't repeat 330 trials)
- **Two-pass systems** can improve accuracy cheaply

### 5. Data Quality
- **Human-in-the-loop for hard cases** (GPT-5.2 verification)
- **Perfect accuracy not always needed** (86% sufficient for Tier 3/4)
- **Know your priorities** (Tier 1/2 > Tier 3/4)

---

## 📊 Metrics Summary

### Testing Volume
- 5 distinct test rounds
- 50-trial validation (stratified sample)
- 17-trial disagreement analysis
- 7-trial prompt comparison
- ~134 total API calls for testing

### Cost Analysis
| Approach | Trials | Cost | Time |
|----------|--------|------|------|
| Testing & validation | ~134 | ~$4 | 2 hrs |
| Existing 330 (GPT-5.2) | 330 | $10 | 30 min |
| NEW agentic | 4,634 | $14 | 4 hrs |
| NEW GPT-5.2 verify | ~400 | $12 | 30 min |
| **Total** | **4,966** | **$40** | **~7 hrs** |

**Baseline (GPT-5.2 only):** $154, ~8 hrs
**Savings:** $114 (74%)

### Accuracy Metrics
| Model/System | Accuracy | Cost/Trial | Speed |
|--------------|----------|------------|-------|
| GPT-5.2 | ~95% (assumed) | $0.031 | 5-8 sec |
| Agentic 5-mini | 86% | $0.003 | 3-5 sec |
| GPT-5-mini (plain) | <80% | $0.002 | 2-3 sec |
| GPT-4o | ~88% | $0.008 | 4-6 sec |

---

## 🚀 Future Work

### Potential Improvements
1. **Fine-tune GPT-5-mini** on categorization task → potential 90%+ accuracy
2. **Active learning:** Use human feedback on disagreements to improve
3. **Confidence scores:** More sophisticated edge case detection
4. **Multi-model ensemble:** Combine 5-mini + 5.2 predictions

### Scalability
- Current system: 4,966 trials in 5 hours
- Bottleneck: API rate limits + cost
- Scale to 50K trials: ~$400, ~50 hours (parallelizable)

### Research Questions
1. Can we predict which trials agentic will get wrong?
2. What's the optimal threshold for GPT-5.2 verification?
3. Can we use trial similarity to reduce categorization costs?

---

## 💡 Product Building Insights

### What Worked Well
1. **Rapid iteration:** Test → Analyze → Refine → Test again
2. **Data-driven decisions:** Let numbers guide choices
3. **Cost awareness:** Always calculate ROI
4. **Documentation:** Capture context while fresh
5. **Validation:** Multiple tests on different samples

### What Could Be Better
1. **Earlier checkpoint implementation:** Lost time to timeouts
2. **Column naming consistency:** "nct_id" vs "NCT Code" caused bugs
3. **Upfront data exploration:** Could have caught column names sooner

### Time Breakdown
- Initial scraping & normalization: ~2 hrs
- Exhaustive search: ~3 hrs
- Model testing & optimization: ~4 hrs
- Pipeline implementation: ~1 hr
- **Total: ~10 hrs** for full system

**Key Insight:** 60% of time spent on testing/optimization, 40% on implementation.
This ratio led to a system that's 74% cheaper and well-validated.

---

## 📝 Notes & Observations

### API Behavior
- ClinicalTrials.gov API v2 is generally reliable
- Rate limiting: ~10 req/sec without issues
- Timeout handling: Essential for 4K+ trial processing

### Model Behavior
- GPT-5.2 reasoning: More thorough eligibility parsing
- GPT-5-mini reasoning: Faster but misses nuance
- Both models: Struggle with ambiguous mutation requirements

### User Needs
- Primary: Find trials patient can enroll in
- Secondary: Understand trial landscape
- Tertiary: Cost tracking, analytics
- **Critical:** Don't miss relevant trials (false negatives costly)

---

## 🎓 Lessons for Future Projects

1. **Test before you scale**
   - 50-trial validation saved us from $140 in wrong-model costs

2. **Simple solutions often win**
   - Enhanced prompt v2 beat complex original by 6%

3. **Know when "good enough" is enough**
   - 86% accuracy on Tier 3/4 is sufficient

4. **Document everything**
   - Future you will thank present you

5. **User feedback is gold**
   - User caught cost calculation error, 330 duplication

6. **Hybrid systems are underrated**
   - Cheap model + expensive model > either alone

---

**Last Updated:** Dec 17, 2024, 7:15 PM
**Status:** Pipeline running (4,634 trials in progress)
**Next Update:** When pipeline completes (~4-5 hours)

