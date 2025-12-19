#!/usr/bin/env python3
"""
ClinicalTrials.gov API Explorer - Comprehensive Term Variations

Testing exhaustive variations of:
1. Colorectal/colon cancer notation
2. KRAS/G12D/RAS/pan-RAS terms
3. Different search fields and their behavior
"""

import requests
import json
from typing import Optional
from collections import defaultdict
import time


BASE_URL = "https://clinicaltrials.gov/api/v2/studies"


def search_trials(
    query_term: Optional[str] = None,
    query_cond: Optional[str] = None,
    query_intr: Optional[str] = None,
    query_spons: Optional[str] = None,
    status_filter: str = "RECRUITING",
    page_size: int = 100,
) -> dict:
    """Search ClinicalTrials.gov API with given parameters."""
    params = {
        "pageSize": page_size,
        "format": "json"
    }
    
    if query_term:
        params["query.term"] = query_term
    if query_cond:
        params["query.cond"] = query_cond
    if query_intr:
        params["query.intr"] = query_intr
    if query_spons:
        params["query.spons"] = query_spons
    if status_filter:
        params["filter.overallStatus"] = status_filter
    
    try:
        response = requests.get(BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        studies = data.get("studies", [])
        total_count = data.get("totalCount", len(studies))
        
        nct_ids = []
        titles = []
        
        for study in studies:
            protocol = study.get("protocolSection", {})
            id_module = protocol.get("identificationModule", {})
            nct_id = id_module.get("nctId", "")
            title = id_module.get("briefTitle", "")
            
            nct_ids.append(nct_id)
            titles.append(title)
        
        return {
            "count": total_count if total_count > 0 else len(studies),
            "nct_ids": nct_ids,
            "titles": titles,
            "params": params
        }
        
    except requests.exceptions.RequestException as e:
        return {"count": 0, "nct_ids": [], "titles": [], "error": str(e)}


def run_searches(searches: list, delay: float = 0.25) -> list:
    """Run multiple searches and return results."""
    results = []
    for search in searches:
        name = search.pop("name")
        result = search_trials(**search)
        result["name"] = name
        result["params"] = search
        results.append(result)
        time.sleep(delay)
    return results


def print_table(results: list, title: str, show_sample: bool = False) -> None:
    """Print results table."""
    print()
    print("=" * 85)
    print(f"  {title}")
    print("=" * 85)
    print()
    
    sorted_results = sorted(results, key=lambda x: len(x["nct_ids"]), reverse=True)
    
    print(f"  {'Search Query':<60} {'Trials':>10}")
    print("  " + "-" * 72)
    
    for r in sorted_results:
        count = len(r["nct_ids"])
        print(f"  {r['name']:<60} {count:>10}")
    
    # Calculate unique across all
    all_ids = set()
    for r in results:
        all_ids.update(r["nct_ids"])
    
    print()
    print(f"  TOTAL UNIQUE across all variations: {len(all_ids)}")
    
    if show_sample and sorted_results and sorted_results[0]["titles"]:
        best = sorted_results[0]
        print()
        print(f"  Top 5 trials from '{best['name']}':")
        for i, (nct, title) in enumerate(zip(best["nct_ids"][:5], best["titles"][:5]), 1):
            short = title[:55] + "..." if len(title) > 55 else title
            print(f"    {i}. {nct}: {short}")


def find_unique_to_each(results: list) -> dict:
    """Find trials unique to each search term."""
    all_ids = set()
    for r in results:
        all_ids.update(r["nct_ids"])
    
    unique_to = {}
    for r in results:
        this_set = set(r["nct_ids"])
        others = set()
        for r2 in results:
            if r2["name"] != r["name"]:
                others.update(r2["nct_ids"])
        unique = this_set - others
        if unique:
            unique_to[r["name"]] = unique
    
    return unique_to


# =============================================================================
# SEARCH FIELD EXPLANATION
# =============================================================================

def explain_search_fields():
    """Explain the different search fields available."""
    print()
    print("#" * 85)
    print("#  UNDERSTANDING ClinicalTrials.gov API SEARCH FIELDS")
    print("#" * 85)
    print()
    print("""
  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │  FIELD              │  WHAT IT SEARCHES                │  BEST FOR              │
  ├─────────────────────────────────────────────────────────────────────────────────┤
  │  query.term         │  ALL text fields (title, desc,   │  General keywords,     │
  │                     │  eligibility, interventions,     │  mutations (KRAS),     │
  │                     │  conditions, everything)         │  biomarkers            │
  ├─────────────────────────────────────────────────────────────────────────────────┤
  │  query.cond         │  ONLY the Conditions field       │  Disease names         │
  │                     │  (what the trial is treating)    │  (colorectal cancer)   │
  ├─────────────────────────────────────────────────────────────────────────────────┤
  │  query.intr         │  ONLY the Interventions field    │  Drug names            │
  │                     │  (drugs, procedures, devices)    │  (RMC-9805, sotorasib) │
  ├─────────────────────────────────────────────────────────────────────────────────┤
  │  query.spons        │  ONLY the Sponsor field          │  Company names         │
  │                     │  (who funds the trial)           │  (Revolution Medicines)│
  └─────────────────────────────────────────────────────────────────────────────────┘

  KEY INSIGHT: 
  - query.term is BROADEST (searches everywhere, may find more but less precise)
  - query.cond/intr/spons are TARGETED (only search specific fields, more precise)

  EXAMPLE - "KRAS":
  - query.term="KRAS" → Finds trials mentioning KRAS ANYWHERE (title, eligibility, etc.)
  - query.cond="KRAS" → Finds trials where KRAS is listed as a CONDITION (rare)
  - query.intr="KRAS" → Finds trials where KRAS is an INTERVENTION (doesn't make sense)

  BEST PRACTICE:
  - Mutations/biomarkers → query.term (they appear in eligibility criteria)
  - Diseases → query.cond (colorectal cancer, etc.)
  - Drugs → query.intr (RMC-9805, sotorasib)
  - Companies → query.spons (Revolution Medicines)
""")


# =============================================================================
# EXHAUSTIVE COLON CANCER VARIATIONS
# =============================================================================

def test_colon_variations_exhaustive():
    """Test ALL variations of colon/colorectal cancer terminology."""
    
    print()
    print("#" * 85)
    print("#  EXHAUSTIVE COLON CANCER TERM VARIATIONS")
    print("#" * 85)
    
    # --- PART 1: Using query.cond (condition field) ---
    cond_searches = [
        # Full names
        {"name": "colorectal cancer", "query_cond": "colorectal cancer"},
        {"name": "colorectal neoplasm", "query_cond": "colorectal neoplasm"},
        {"name": "colorectal carcinoma", "query_cond": "colorectal carcinoma"},
        {"name": "colorectal adenocarcinoma", "query_cond": "colorectal adenocarcinoma"},
        {"name": "colorectal tumor", "query_cond": "colorectal tumor"},
        {"name": "colorectal malignancy", "query_cond": "colorectal malignancy"},
        
        # Just colorectal
        {"name": "colorectal", "query_cond": "colorectal"},
        
        # Colon variants
        {"name": "colon cancer", "query_cond": "colon cancer"},
        {"name": "colon carcinoma", "query_cond": "colon carcinoma"},
        {"name": "colon adenocarcinoma", "query_cond": "colon adenocarcinoma"},
        {"name": "colon neoplasm", "query_cond": "colon neoplasm"},
        {"name": "colon tumor", "query_cond": "colon tumor"},
        {"name": "colon", "query_cond": "colon"},
        
        # Rectal variants
        {"name": "rectal cancer", "query_cond": "rectal cancer"},
        {"name": "rectal carcinoma", "query_cond": "rectal carcinoma"},
        {"name": "rectal adenocarcinoma", "query_cond": "rectal adenocarcinoma"},
        {"name": "rectal", "query_cond": "rectal"},
        
        # Abbreviations
        {"name": "CRC", "query_cond": "CRC"},
        {"name": "mCRC", "query_cond": "mCRC"},
        {"name": "metastatic colorectal", "query_cond": "metastatic colorectal"},
        {"name": "metastatic CRC", "query_cond": "metastatic CRC"},
        
        # Staging
        {"name": "stage IV colorectal", "query_cond": "stage IV colorectal"},
        {"name": "advanced colorectal", "query_cond": "advanced colorectal"},
        
        # Boolean combinations
        {"name": "colorectal OR colon", "query_cond": "colorectal OR colon"},
        {"name": "colorectal OR colon OR rectal", "query_cond": "colorectal OR colon OR rectal"},
        {"name": "colorectal OR CRC", "query_cond": "colorectal OR CRC"},
        {"name": "(colorectal OR colon) AND cancer", "query_cond": "(colorectal OR colon) AND cancer"},
    ]
    
    cond_results = run_searches(cond_searches)
    print_table(cond_results, "CONDITION FIELD (query.cond) - Colon Cancer Variations")
    
    # Find unique trials
    unique = find_unique_to_each(cond_results)
    if unique:
        print()
        print("  TRIALS UNIQUE TO SPECIFIC TERMS (only found with this term):")
        for name, ids in sorted(unique.items(), key=lambda x: -len(x[1])):
            print(f"    '{name}': {len(ids)} unique trials")
    
    # --- PART 2: Using query.term (general search) ---
    term_searches = [
        {"name": "term: colorectal cancer", "query_term": "colorectal cancer"},
        {"name": "term: colon cancer", "query_term": "colon cancer"},
        {"name": "term: CRC", "query_term": "CRC"},
        {"name": "term: mCRC", "query_term": "mCRC"},
        {"name": "term: colorectal", "query_term": "colorectal"},
    ]
    
    term_results = run_searches(term_searches)
    print_table(term_results, "GENERAL TERM (query.term) - Colon Cancer Variations")
    
    # Compare cond vs term
    print()
    print("  COMPARISON: query.cond vs query.term")
    cond_colorectal = set(next(r["nct_ids"] for r in cond_results if r["name"] == "colorectal cancer"))
    term_colorectal = set(next(r["nct_ids"] for r in term_results if r["name"] == "term: colorectal cancer"))
    
    only_cond = cond_colorectal - term_colorectal
    only_term = term_colorectal - cond_colorectal
    both = cond_colorectal & term_colorectal
    
    print(f"    'colorectal cancer' in BOTH fields: {len(both)}")
    print(f"    Only in query.cond: {len(only_cond)}")
    print(f"    Only in query.term: {len(only_term)}")
    
    return cond_results, term_results


# =============================================================================
# EXHAUSTIVE KRAS/G12D/RAS VARIATIONS
# =============================================================================

def test_kras_variations_exhaustive():
    """Test ALL variations of KRAS/G12D/RAS terminology."""
    
    print()
    print("#" * 85)
    print("#  EXHAUSTIVE KRAS / G12D / RAS TERM VARIATIONS")
    print("#" * 85)
    
    # All searches use query.term since mutations appear in eligibility text
    searches = [
        # --- G12D specific ---
        {"name": "G12D", "query_term": "G12D"},
        {"name": "KRAS G12D", "query_term": "KRAS G12D"},
        {"name": "KRAS-G12D", "query_term": "KRAS-G12D"},
        {"name": "KRAS(G12D)", "query_term": "KRAS(G12D)"},
        {"name": "\"G12D\"", "query_term": '"G12D"'},
        
        # --- Other G12 mutations ---
        {"name": "G12C", "query_term": "G12C"},
        {"name": "G12V", "query_term": "G12V"},
        {"name": "G12R", "query_term": "G12R"},
        {"name": "G12A", "query_term": "G12A"},
        {"name": "G12S", "query_term": "G12S"},
        {"name": "G12 (any)", "query_term": "G12"},
        
        # --- G13 mutations ---
        {"name": "G13D", "query_term": "G13D"},
        {"name": "G13C", "query_term": "G13C"},
        {"name": "G13 (any)", "query_term": "G13"},
        
        # --- KRAS general ---
        {"name": "KRAS", "query_term": "KRAS"},
        {"name": "KRAS mutation", "query_term": "KRAS mutation"},
        {"name": "KRAS mutant", "query_term": "KRAS mutant"},
        {"name": "KRAS-mutant", "query_term": "KRAS-mutant"},
        {"name": "KRAS positive", "query_term": "KRAS positive"},
        {"name": "KRAS+", "query_term": "KRAS+"},
        {"name": "mutant KRAS", "query_term": "mutant KRAS"},
        {"name": "KRAS mutated", "query_term": "KRAS mutated"},
        
        # --- RAS general ---
        {"name": "RAS", "query_term": "RAS"},
        {"name": "RAS mutation", "query_term": "RAS mutation"},
        {"name": "RAS mutant", "query_term": "RAS mutant"},
        {"name": "RAS-mutant", "query_term": "RAS-mutant"},
        
        # --- Pan-RAS ---
        {"name": "pan-RAS", "query_term": "pan-RAS"},
        {"name": "pan RAS", "query_term": "pan RAS"},
        {"name": "panRAS", "query_term": "panRAS"},
        {"name": "RAS(ON)", "query_term": "RAS(ON)"},
        {"name": "RASON", "query_term": "RASON"},
        
        # --- NRAS/HRAS ---
        {"name": "NRAS", "query_term": "NRAS"},
        {"name": "HRAS", "query_term": "HRAS"},
        
        # --- Boolean combinations ---
        {"name": "KRAS OR NRAS", "query_term": "KRAS OR NRAS"},
        {"name": "KRAS OR NRAS OR HRAS", "query_term": "KRAS OR NRAS OR HRAS"},
        {"name": "G12D OR G12C OR G12V", "query_term": "G12D OR G12C OR G12V"},
        {"name": "G12 OR G13", "query_term": "G12 OR G13"},
        {"name": "KRAS AND mutation", "query_term": "KRAS AND mutation"},
    ]
    
    results = run_searches(searches)
    print_table(results, "KRAS / G12D / RAS Variations (query.term)", show_sample=True)
    
    # Find unique trials
    unique = find_unique_to_each(results)
    if unique:
        print()
        print("  TRIALS UNIQUE TO SPECIFIC TERMS (only found with this term):")
        for name, ids in sorted(unique.items(), key=lambda x: -len(x[1]))[:15]:
            print(f"    '{name}': {len(ids)} unique trials")
    
    # Key comparisons
    print()
    print("  KEY COMPARISONS:")
    
    g12d = set(next(r["nct_ids"] for r in results if r["name"] == "G12D"))
    kras_g12d = set(next(r["nct_ids"] for r in results if r["name"] == "KRAS G12D"))
    kras = set(next(r["nct_ids"] for r in results if r["name"] == "KRAS"))
    ras = set(next(r["nct_ids"] for r in results if r["name"] == "RAS"))
    g12c = set(next(r["nct_ids"] for r in results if r["name"] == "G12C"))
    
    print(f"    G12D alone: {len(g12d)} | KRAS G12D: {len(kras_g12d)} | Diff: {len(g12d - kras_g12d)}")
    print(f"    KRAS: {len(kras)} | RAS: {len(ras)} | KRAS not in RAS: {len(kras - ras)}")
    print(f"    G12D: {len(g12d)} | G12C: {len(g12c)} | Overlap: {len(g12d & g12c)}")
    
    return results


# =============================================================================
# COMBINED SEARCH - MAXIMIZING COVERAGE
# =============================================================================

def test_combined_maximum_coverage():
    """Test combined searches to maximize coverage for Tier 1."""
    
    print()
    print("#" * 85)
    print("#  COMBINED SEARCHES - FINDING MAXIMUM COVERAGE")
    print("#" * 85)
    
    searches = [
        # Narrow (Tier 1 - G12D + colorectal)
        {"name": "G12D + colorectal", "query_term": "G12D", "query_cond": "colorectal"},
        {"name": "G12D + colon", "query_term": "G12D", "query_cond": "colon"},
        {"name": "G12D + CRC", "query_term": "G12D", "query_cond": "CRC"},
        {"name": "G12D + colorectal OR colon", "query_term": "G12D", "query_cond": "colorectal OR colon"},
        {"name": "G12D + colorectal OR colon OR CRC", "query_term": "G12D", "query_cond": "colorectal OR colon OR CRC"},
        
        # Slightly broader (KRAS + colorectal)
        {"name": "KRAS + colorectal", "query_term": "KRAS", "query_cond": "colorectal"},
        {"name": "KRAS + colorectal OR colon OR CRC", "query_term": "KRAS", "query_cond": "colorectal OR colon OR CRC"},
        {"name": "KRAS mutation + colorectal", "query_term": "KRAS mutation", "query_cond": "colorectal"},
        
        # Broader (RAS + colorectal)
        {"name": "RAS + colorectal", "query_term": "RAS", "query_cond": "colorectal"},
        {"name": "RAS + colorectal OR colon OR CRC", "query_term": "RAS", "query_cond": "colorectal OR colon OR CRC"},
        
        # Very broad
        {"name": "KRAS OR RAS + colorectal", "query_term": "KRAS OR RAS", "query_cond": "colorectal"},
        {"name": "mutation + colorectal", "query_term": "mutation", "query_cond": "colorectal"},
    ]
    
    results = run_searches(searches)
    print_table(results, "COMBINED SEARCHES (term + condition)", show_sample=True)
    
    # Show progression from narrow to broad
    print()
    print("  COVERAGE PROGRESSION (narrow → broad):")
    
    g12d_colorectal = set(next(r["nct_ids"] for r in results if r["name"] == "G12D + colorectal"))
    g12d_all_colon = set(next(r["nct_ids"] for r in results if r["name"] == "G12D + colorectal OR colon OR CRC"))
    kras_colorectal = set(next(r["nct_ids"] for r in results if r["name"] == "KRAS + colorectal"))
    kras_all_colon = set(next(r["nct_ids"] for r in results if r["name"] == "KRAS + colorectal OR colon OR CRC"))
    ras_all_colon = set(next(r["nct_ids"] for r in results if r["name"] == "RAS + colorectal OR colon OR CRC"))
    
    print(f"    G12D + colorectal only:              {len(g12d_colorectal):>3} trials")
    print(f"    G12D + (colorectal|colon|CRC):       {len(g12d_all_colon):>3} trials (+{len(g12d_all_colon - g12d_colorectal)})")
    print(f"    KRAS + colorectal:                   {len(kras_colorectal):>3} trials")
    print(f"    KRAS + (colorectal|colon|CRC):       {len(kras_all_colon):>3} trials (+{len(kras_all_colon - kras_colorectal)})")
    print(f"    RAS + (colorectal|colon|CRC):        {len(ras_all_colon):>3} trials")
    
    # What does KRAS catch that G12D doesn't?
    kras_not_g12d = kras_all_colon - g12d_all_colon
    print()
    print(f"  KRAS catches {len(kras_not_g12d)} trials that G12D misses (other KRAS mutations)")
    
    return results


# =============================================================================
# MAIN
# =============================================================================

def run_all_tests():
    """Run all exploration tests."""
    print()
    print("=" * 85)
    print("=" * 85)
    print("  ClinicalTrials.gov API - EXHAUSTIVE SEARCH TERM EXPLORATION")
    print("=" * 85)
    print("=" * 85)
    
    # Explain fields first
    explain_search_fields()
    
    # Run tests
    colon_cond, colon_term = test_colon_variations_exhaustive()
    kras_results = test_kras_variations_exhaustive()
    combined_results = test_combined_maximum_coverage()
    
    # Final summary
    print()
    print("=" * 85)
    print("  FINAL RECOMMENDATIONS")
    print("=" * 85)
    print()
    print("  FOR MAXIMUM COVERAGE:")
    print()
    print("  1. COLORECTAL CONDITION - use:")
    print("     query.cond = 'colorectal OR colon OR rectal OR CRC OR mCRC'")
    print()
    print("  2. KRAS/G12D MUTATION - use:")
    print("     query.term = 'G12D' (for Tier 1)")
    print("     query.term = 'KRAS OR NRAS' (for broader Tier 2)")
    print("     query.term = 'RAS' (for broadest)")
    print()
    print("  3. COMBINED (Tier 1 - G12D + Colorectal):")
    print("     query.term = 'G12D'")
    print("     query.cond = 'colorectal OR colon OR CRC'")
    print()
    print("  4. DON'T FORGET:")
    print("     - Include NOT_YET_RECRUITING status for upcoming trials")
    print("     - 'G12D' alone finds slightly more than 'KRAS G12D'")
    print("     - Some trials only use 'CRC' abbreviation, not 'colorectal'")
    print()


if __name__ == "__main__":
    run_all_tests()
