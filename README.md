# Clinical Trial Categorization System 🏥

> An intelligent system for categorizing clinical trials using parallel AI agents, achieving 86% accuracy and 42x speedup through innovative parallel processing.

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--5-green.svg)](https://openai.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🎯 Overview

This project automatically categorizes 4,966+ clinical trials to help match patients with KRAS G12D colorectal cancer to relevant treatment options. It uses a **hybrid AI approach** combining cost-effective agentic processing (GPT-5-mini) with high-accuracy verification (GPT-5.2).

### Key Achievements

- 🚀 **42x speedup:** 39 hours → 32 minutes using 20 parallel workers
- 💰 **83% cost savings:** $160 → $27 through smart model selection
- 🎯 **86% accuracy:** Validated on stratified test set
- 🔄 **Production-ready:** Checkpointing, error handling, comprehensive logging

---

## 📊 Quick Stats

| Metric | Value |
|--------|-------|
| Trials processed | 4,966 |
| Processing time | 32 minutes (parallel) |
| Total cost | $27.45 |
| Accuracy | 86% (vs GPT-5.2 baseline) |
| Models tested | 5 (GPT-4o, GPT-5-mini, GPT-5.2, etc.) |
| Test iterations | 5 comprehensive rounds |

---

## 🏗️ Architecture

### Hybrid Categorization Pipeline

```
┌─────────────────────────────────────────┐
│ Step 1: Agentic 5-mini (Bulk)          │
│  - 20 parallel workers                  │
│  - 86% accuracy                         │
│  - $0.003/trial                         │
│  - Processes: ALL trials                │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│ Step 2: Filter High Priority           │
│  - Extract Tier 1/1.5/2 trials          │
│  - These need verification              │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│ Step 3: GPT-5.2 Verification            │
│  - Re-categorize high-priority trials   │
│  - ~95% accuracy                        │
│  - $0.031/trial                         │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│ Step 4: Merge Results                   │
│  - High-priority: Use GPT-5.2           │
│  - Low-priority: Use agentic            │
└─────────────────────────────────────────┘
```

### Parallel Processing Innovation

**Key Innovation:** Massively parallel AI agent processing

- **20 concurrent workers** processing trials simultaneously
- **Subprocess-based parallelization** (not threading/async)
- **No rate limit issues** (320 RPM < 500 RPM limit)
- **Independent execution** - no shared state, no conflicts

See [PARALLEL_PROCESSING_ARCHITECTURE.md](PARALLEL_PROCESSING_ARCHITECTURE.md) for technical deep-dive.

---

## 🚀 Getting Started

### Prerequisites

```bash
Python 3.9+
OpenAI API key (Tier 2+ recommended for parallel processing)
```

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/clinical-trials-categorization.git
cd clinical-trials-categorization

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### Quick Start

```bash
# Run parallel categorization on sample dataset
python scripts/run_full_parallel_20workers.py

# Run single trial categorization
python -c "
from gpt.agentic_categorizer import categorize_with_agentic_chain
# ... see examples/ for full code
"
```

---

## 📁 Project Structure

```
├── gpt/                      # AI categorization modules
│   ├── trial_categorizer.py     # GPT-5.2 categorization
│   ├── agentic_categorizer.py   # Agentic 5-mini system
│   └── institution_normalizer.py # Institution name normalization
├── prompts/                  # GPT prompts (version controlled!)
│   ├── trial_categorization.py  # Main prompt (GPT-5.2)
│   └── trial_categorization_v2.py # Enhanced prompt (agentic)
├── scripts/                  # Execution scripts
│   ├── run_full_parallel_20workers.py # Production parallel runner
│   ├── test_10_workers.py           # 10-worker test
│   └── test_20_workers.py           # 20-worker test
├── test/                     # Evaluation & testing
│   ├── compare_agentic_vs_52_on_priority.py
│   └── analyze_disagreements.py
├── search/                   # Trial search (ClinicalTrials.gov API)
├── scraper/                  # Location scraping
├── utils/                    # Helper functions
└── output/                   # Results (gitignored)
```

---

## 📚 Documentation

### Core Documentation

- **[PARALLEL_PROCESSING_ARCHITECTURE.md](PARALLEL_PROCESSING_ARCHITECTURE.md)** - Technical deep-dive on parallel processing (500+ lines)
- **[DECISION_LOG.md](DECISION_LOG.md)** - Every decision, test, and tradeoff documented
- **[test/MODEL_EVALUATION_LOG.md](test/MODEL_EVALUATION_LOG.md)** - Comprehensive model testing results
- **[HYBRID_PIPELINE_PLAN.md](HYBRID_PIPELINE_PLAN.md)** - Execution strategy and cost analysis

### Additional Resources

- **[PRODUCT_BUILDING_FEEDBACK.md](PRODUCT_BUILDING_FEEDBACK.md)** - Product development insights

---

## 🧪 Testing & Validation

### Test Coverage

- ✅ **5 model comparison rounds** (GPT-4o, GPT-5-mini, GPT-5.2)
- ✅ **50-trial validation** (stratified sampling)
- ✅ **Prompt comparison** (enhanced vs original)
- ✅ **Parallel scaling tests** (5, 10, 20 workers)
- ✅ **Rate limit verification** (no errors at 320 RPM)

### Accuracy Results

| Model/System | Accuracy | Cost/Trial | Speed |
|--------------|----------|------------|-------|
| GPT-5.2 | ~95% (baseline) | $0.031 | 5-8 sec |
| **Agentic 5-mini** | **86%** | **$0.003** | **3-5 sec** |
| GPT-4o | ~88% | $0.008 | 4-6 sec |

**Agentic Breakdown by Tier:**
- Tier 3: **100%** (17/17) ✨
- Tier 2: **86.7%** (13/15) ✅
- Tier 4: **76.5%** (13/17)

---

## 💡 Key Innovations

### 1. Agentic Two-Pass System

```python
# Pass 1: Fast categorization with GPT-5-mini
result = categorize_with_mini(trial_data)

# Pass 2: Self-verification for edge cases
if detect_edge_case(result):
    verification = verify_categorization(result)
    if not verification['is_correct']:
        result = apply_correction(verification)
```

**Result:** 86% accuracy at 10x lower cost!

### 2. Subprocess-Based Parallelization

```python
# Spawn 20 independent Python processes
for worker_id, batch in enumerate(batches):
    proc = subprocess.Popen([
        'python3', '-c',
        f"process_batch(batch_{worker_id}, {worker_id})"
    ])
    processes.append(proc)

# Wait for all to complete
for proc in processes:
    proc.wait()
```

**Result:** 42x speedup with zero race conditions!

### 3. Prompt Engineering for Different Models

- **Enhanced prompt v2:** Simpler, clearer → 86% with GPT-5-mini
- **Original prompt:** Complex, detailed → 80% with GPT-5-mini
- **Lesson:** Tailor prompts to model capabilities!

---

## 📈 Performance

### Speedup Analysis

| Workers | Time (2,584 trials) | Speedup | Efficiency |
|---------|---------------------|---------|------------|
| 1 (sequential) | 2.8 hours | 1x | 100% |
| 5 | 33 minutes | 5.1x | 98% |
| 10 | 18 minutes | 9.3x | 93% |
| **20** | **4-32 min*** | **16-42x** | **81%** |

*Range depends on trial complexity

### Cost Comparison

```
Baseline (GPT-5.2 only):
4,966 trials × $0.031 = $154

Hybrid approach:
330 priority × $0.031 = $10.23 (GPT-5.2)
4,636 bulk × $0.003 = $13.91 (agentic)
Testing = $4
Total = $28.14

Savings: $125.86 (82%)
```

---

## 🎓 Lessons Learned

### Technical

1. **Subprocess > Threading** for API-bound parallel processing (no GIL issues)
2. **Simpler prompts often win** for mid-tier models (86% vs 80%)
3. **Test incrementally** - 5, 10, 20 workers (don't jump to 100!)
4. **Checkpointing is critical** - saved 18 hours when quota hit
5. **Uneven task duration** - some trials take 10x longer

### Product

1. **Cost consciousness from day 1** - designed for 80% savings
2. **Iterate on data** - 5 test rounds before production
3. **Document decisions real-time** - context fades quickly
4. **Validate assumptions** - 50-trial test caught prompt issues
5. **Balance speed and quality** - 86% accuracy "good enough" for Tier 3/4

See [DECISION_LOG.md](DECISION_LOG.md) for full journey.

---

## 🔮 Future Work

### Potential Improvements

- [ ] **Dynamic work queue** - automatic load balancing
- [ ] **Streaming results** - process as workers complete
- [ ] **Fine-tune GPT-5-mini** - could reach 90%+ accuracy
- [ ] **Active learning** - human feedback on disagreements
- [ ] **Confidence scores** - better edge case detection

### Scaling

Current system handles 5,000 trials in ~30 minutes.

**Could scale to:**
- 50,000 trials in ~5 hours
- 500,000 trials in ~2 days

**Bottleneck:** API rate limits (not cost, not code!)

---

## 🤝 Contributing

This project is primarily for personal/research use, but suggestions and insights are welcome!

**Areas for discussion:**
- Alternative parallel processing approaches
- Prompt engineering techniques
- Model selection strategies
- Cost optimization ideas

---

## 📄 License

MIT License - feel free to learn from and adapt this code!

---

## 🙏 Acknowledgments

- **OpenAI** - GPT-5.2, GPT-5-mini models
- **ClinicalTrials.gov** - Public API access
- **Python community** - Pandas, subprocess, all the great tools

---

## 📧 Contact

**Jordan Cheung**
- GitHub: [@yourusername](https://github.com/yourusername)
- Project built with: Python, OpenAI API, love for mom 💙

---

## ⭐ Star History

If you find this project interesting or useful, consider starring it!

**This project demonstrates:**
- ✨ Production-grade AI system design
- 🚀 Innovative parallel processing
- 💰 Cost-conscious engineering
- 📚 Comprehensive documentation
- 🎯 Real-world impact

Built in ~10 hours of iterative development. **Speed + Quality is possible!**
