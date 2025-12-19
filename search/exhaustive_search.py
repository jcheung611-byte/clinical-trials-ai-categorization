#!/usr/bin/env python3
"""
Exhaustive Clinical Trial Search Tool

Runs comprehensive API queries for all RAS/colon-related terms,
deduplicates results, categorizes by mutation and cancer type,
assigns priority tiers, and compares against existing spreadsheet.

Features:
- Retry logic with exponential backoff
- Incremental saving after each phase
- Resume capability from checkpoints
"""

import requests
import json
import re
import time
import pandas as pd
from typing import Optional, Dict, List, Set, Tuple
from pathlib import Path
from datetime import datetime


BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
SCRIPT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = SCRIPT_DIR / "output"
CHECKPOINT_FILE = OUTPUT_DIR / "search_checkpoint.json"

# =============================================================================
# SEARCH TERM DEFINITIONS
# =============================================================================

# Mutation terms - search in query.term (appears in eligibility text)
MUTATION_TERMS = [
    # G12D specific
    "G12D",
    "KRAS G12D",
    "KRAS-G12D",
    
    # Other G12 mutations
    "G12C",
    "G12V", 
    "G12R",
    "G12A",
    "G12S",
    "G12",  # Catches all G12x
    
    # G13 mutations
    "G13D",
    "G13C",
    "G13",
    
    # KRAS general
    "KRAS",
    "KRAS mutation",
    "KRAS mutant",
    "KRAS positive",
    "KRAS mutated",
    
    # NRAS/HRAS
    "NRAS",
    "HRAS",
    
    # RAS general
    "RAS",
    "RAS mutation",
    "RAS mutant",
    "RAS(ON)",
    "pan-RAS",
    "pan RAS",
]

# Cancer terms - search in query.cond (condition field)
CANCER_TERMS = [
    # Colorectal
    "colorectal cancer",
    "colorectal",
    "colorectal carcinoma",
    "colorectal adenocarcinoma",
    "colorectal neoplasm",
    
    # Colon
    "colon cancer",
    "colon",
    "colon carcinoma",
    "colon adenocarcinoma",
    
    # Rectal
    "rectal cancer",
    "rectal",
    "rectal carcinoma",
    
    # Abbreviations
    "CRC",
    "mCRC",
    "metastatic colorectal",
    "metastatic CRC",
    "advanced colorectal",
    "stage IV colorectal",
    
    # Broader GI
    "gastrointestinal cancer",
    "gastrointestinal",
    "GI cancer",
    "solid tumor",
    "solid tumors",
]


# =============================================================================
# CHECKPOINT / PROGRESS SAVING
# =============================================================================

def save_checkpoint(data: Dict, filename: str = "search_checkpoint.json"):
    """Save current progress to checkpoint file."""
    filepath = OUTPUT_DIR / filename
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=list)
    print(f"  [Checkpoint saved: {len(data.get('all_nct_ids', []))} NCT IDs]")


def load_checkpoint(filename: str = "search_checkpoint.json") -> Optional[Dict]:
    """Load checkpoint if it exists."""
    filepath = OUTPUT_DIR / filename
    if filepath.exists():
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            # Convert lists back to sets
            if 'all_nct_ids' in data:
                data['all_nct_ids'] = set(data['all_nct_ids'])
            if 'search_results' in data:
                for k, v in data['search_results'].items():
                    data['search_results'][k] = set(v)
            return data
        except Exception as e:
            print(f"  Warning: Could not load checkpoint: {e}")
    return None


def save_nct_ids_incrementally(nct_ids: Set[str], filename: str = "found_nct_ids.txt"):
    """Save NCT IDs to a simple text file for safety."""
    filepath = OUTPUT_DIR / filename
    with open(filepath, 'w') as f:
        for nct_id in sorted(nct_ids):
            f.write(f"{nct_id}\n")


# =============================================================================
# API SEARCH FUNCTIONS WITH RETRY LOGIC
# =============================================================================

def search_api(
    query_term: Optional[str] = None,
    query_cond: Optional[str] = None,
    status_filter: str = "RECRUITING,NOT_YET_RECRUITING",
    page_size: int = 100,
    max_pages: int = 10,
    max_retries: int = 3,
    base_delay: float = 2.0
) -> List[str]:
    """
    Search ClinicalTrials.gov API and return list of NCT IDs.
    Handles pagination and includes retry logic with exponential backoff.
    """
    all_nct_ids = []
    page_token = None
    pages_fetched = 0
    
    while pages_fetched < max_pages:
        params = {
            "pageSize": page_size,
            "format": "json"
        }
        
        if query_term:
            params["query.term"] = query_term
        if query_cond:
            params["query.cond"] = query_cond
        if status_filter:
            params["filter.overallStatus"] = status_filter
        if page_token:
            params["pageToken"] = page_token
        
        # Retry loop with exponential backoff
        success = False
        for attempt in range(max_retries):
            try:
                response = requests.get(BASE_URL, params=params, timeout=60)
                response.raise_for_status()
                data = response.json()
                
                studies = data.get("studies", [])
                
                for study in studies:
                    protocol = study.get("protocolSection", {})
                    id_module = protocol.get("identificationModule", {})
                    nct_id = id_module.get("nctId", "")
                    if nct_id:
                        all_nct_ids.append(nct_id)
                
                # Check for next page
                next_page_token = data.get("nextPageToken")
                if not next_page_token or len(studies) < page_size:
                    return all_nct_ids  # Done
                
                page_token = next_page_token
                pages_fetched += 1
                success = True
                time.sleep(0.5)  # Brief pause between pages
                break
                
            except requests.exceptions.Timeout:
                delay = base_delay * (2 ** attempt)
                print(f" [timeout, retry {attempt+1}/{max_retries}, waiting {delay:.1f}s]", end="", flush=True)
                time.sleep(delay)
            except requests.exceptions.RequestException as e:
                delay = base_delay * (2 ** attempt)
                print(f" [error, retry {attempt+1}/{max_retries}]", end="", flush=True)
                time.sleep(delay)
        
        if not success:
            print(f" [failed after {max_retries} retries]", end="", flush=True)
            break
    
    return all_nct_ids


def run_all_searches(resume_from: Optional[Dict] = None) -> Dict[str, Set[str]]:
    """
    Run all search combinations and collect NCT IDs.
    Supports resuming from checkpoint.
    """
    results = resume_from.get('search_results', {}) if resume_from else {}
    completed_searches = set(results.keys())
    
    print("=" * 80)
    print("PHASE 1: Running exhaustive API searches")
    print("=" * 80)
    
    if completed_searches:
        print(f"  Resuming from checkpoint: {len(completed_searches)} searches already done")
    
    # 1. Mutation terms alone
    print("\n--- Mutation term searches (query.term) ---")
    for i, term in enumerate(MUTATION_TERMS, 1):
        search_key = f"term:{term}"
        if search_key in completed_searches:
            print(f"  [{i}/{len(MUTATION_TERMS)}] {term}: SKIPPED (already done)")
            continue
        
        print(f"  [{i}/{len(MUTATION_TERMS)}] Searching: {term}...", end=" ", flush=True)
        nct_ids = search_api(query_term=term)
        results[search_key] = set(nct_ids)
        print(f"{len(nct_ids)} trials")
        time.sleep(0.5)
    
    # Save checkpoint after mutation searches
    all_nct_ids = set()
    for nct_set in results.values():
        all_nct_ids.update(nct_set)
    save_checkpoint({
        'phase': 'mutation_complete',
        'search_results': {k: list(v) for k, v in results.items()},
        'all_nct_ids': list(all_nct_ids)
    })
    
    # 2. Cancer terms alone
    print("\n--- Cancer term searches (query.cond) ---")
    for i, term in enumerate(CANCER_TERMS, 1):
        search_key = f"cond:{term}"
        if search_key in completed_searches:
            print(f"  [{i}/{len(CANCER_TERMS)}] {term}: SKIPPED (already done)")
            continue
        
        print(f"  [{i}/{len(CANCER_TERMS)}] Searching: {term}...", end=" ", flush=True)
        nct_ids = search_api(query_cond=term)
        results[search_key] = set(nct_ids)
        print(f"{len(nct_ids)} trials")
        time.sleep(0.5)
    
    # Save checkpoint after cancer searches
    all_nct_ids = set()
    for nct_set in results.values():
        all_nct_ids.update(nct_set)
    save_checkpoint({
        'phase': 'cancer_complete',
        'search_results': {k: list(v) for k, v in results.items()},
        'all_nct_ids': list(all_nct_ids)
    })
    
    # 3. Key cross-combinations
    print("\n--- Combined searches (mutation + cancer) ---")
    key_mutations = ["G12D", "G12C", "KRAS", "RAS", "NRAS", "pan-RAS"]
    key_cancers = ["colorectal", "colon", "CRC", "mCRC", "gastrointestinal"]
    total_combined = len(key_mutations) * len(key_cancers)
    combo_num = 0
    
    for mut in key_mutations:
        for cancer in key_cancers:
            combo_num += 1
            search_key = f"term:{mut}+cond:{cancer}"
            if search_key in completed_searches:
                print(f"  [{combo_num}/{total_combined}] {mut} + {cancer}: SKIPPED")
                continue
            
            print(f"  [{combo_num}/{total_combined}] Searching: {mut} + {cancer}...", end=" ", flush=True)
            nct_ids = search_api(query_term=mut, query_cond=cancer)
            results[search_key] = set(nct_ids)
            print(f"{len(nct_ids)} trials")
            time.sleep(0.5)
    
    # Save final checkpoint
    all_nct_ids = set()
    for nct_set in results.values():
        all_nct_ids.update(nct_set)
    save_checkpoint({
        'phase': 'searches_complete',
        'search_results': {k: list(v) for k, v in results.items()},
        'all_nct_ids': list(all_nct_ids)
    })
    save_nct_ids_incrementally(all_nct_ids)
    
    return results


def deduplicate_results(search_results: Dict[str, Set[str]]) -> Tuple[Set[str], Dict[str, List[str]]]:
    """
    Deduplicate NCT IDs across all searches.
    """
    all_nct_ids = set()
    nct_to_searches = {}
    
    for search_key, nct_set in search_results.items():
        for nct_id in nct_set:
            all_nct_ids.add(nct_id)
            if nct_id not in nct_to_searches:
                nct_to_searches[nct_id] = []
            nct_to_searches[nct_id].append(search_key)
    
    print(f"\n{'=' * 80}")
    print(f"DEDUPLICATION: {len(all_nct_ids)} unique trials from {len(search_results)} searches")
    print(f"{'=' * 80}")
    
    return all_nct_ids, nct_to_searches


# =============================================================================
# TRIAL DETAILS FETCHING WITH RETRY
# =============================================================================

def fetch_trial_details(nct_id: str, max_retries: int = 3, base_delay: float = 2.0) -> Optional[Dict]:
    """
    Fetch full trial details from API for a single NCT ID.
    Includes retry logic with exponential backoff.
    """
    url = f"{BASE_URL}/{nct_id}"
    params = {"format": "json"}
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            delay = base_delay * (2 ** attempt)
            time.sleep(delay)
        except requests.exceptions.RequestException:
            delay = base_delay * (2 ** attempt)
            time.sleep(delay)
    
    return None


def extract_trial_info(study_data: Dict) -> Dict:
    """
    Extract relevant fields from API response.
    """
    protocol = study_data.get("protocolSection", {})
    
    # Identification
    id_module = protocol.get("identificationModule", {})
    nct_id = id_module.get("nctId", "")
    title = id_module.get("briefTitle", "")
    
    # Status
    status_module = protocol.get("statusModule", {})
    overall_status = status_module.get("overallStatus", "")
    
    # Conditions
    conditions_module = protocol.get("conditionsModule", {})
    conditions = conditions_module.get("conditions", [])
    
    # Interventions
    arms_module = protocol.get("armsInterventionsModule", {})
    interventions = arms_module.get("interventions", [])
    intervention_names = [i.get("name", "") for i in interventions]
    
    # Sponsor
    sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
    lead_sponsor = sponsor_module.get("leadSponsor", {})
    sponsor_name = lead_sponsor.get("name", "")
    
    # Eligibility (for mutation detection)
    eligibility_module = protocol.get("eligibilityModule", {})
    eligibility_text = eligibility_module.get("eligibilityCriteria", "")
    
    # Description
    description_module = protocol.get("descriptionModule", {})
    brief_summary = description_module.get("briefSummary", "")
    
    return {
        "nct_id": nct_id,
        "title": title,
        "status": overall_status,
        "conditions": conditions,
        "interventions": intervention_names,
        "sponsor": sponsor_name,
        "eligibility_text": eligibility_text,
        "brief_summary": brief_summary,
        "all_text": f"{title} {' '.join(conditions)} {eligibility_text} {brief_summary}".upper()
    }


# =============================================================================
# CATEGORIZATION
# =============================================================================

def detect_mutation_type(trial_info: Dict, matched_searches: List[str]) -> str:
    """
    Determine the most specific mutation type for this trial.
    """
    all_text = trial_info["all_text"]
    
    if "G12D" in all_text:
        return "G12D"
    if "G12C" in all_text:
        return "G12C"
    if "G12V" in all_text:
        return "G12V"
    if "G12R" in all_text:
        return "G12R"
    if "G12A" in all_text:
        return "G12A"
    if "G12S" in all_text:
        return "G12S"
    if re.search(r"\bG12\b", all_text):
        return "G12"
    if "G13D" in all_text:
        return "G13D"
    if re.search(r"\bG13\b", all_text):
        return "G13"
    if "PAN-RAS" in all_text or "PAN RAS" in all_text or "PANRAS" in all_text:
        return "Pan-RAS"
    if "RAS(ON)" in all_text or "RASON" in all_text:
        return "RAS(ON)"
    if "KRAS" in all_text:
        return "KRAS"
    if "NRAS" in all_text:
        return "NRAS"
    if "HRAS" in all_text:
        return "HRAS"
    if re.search(r"\bRAS\b", all_text):
        return "RAS"
    
    for search in matched_searches:
        if "G12D" in search:
            return "G12D"
        if "G12C" in search:
            return "G12C"
        if "KRAS" in search:
            return "KRAS"
        if "RAS" in search:
            return "RAS"
    
    return "None"


def detect_cancer_type(trial_info: Dict, matched_searches: List[str]) -> str:
    """
    Determine the cancer type for this trial.
    """
    all_text = trial_info["all_text"]
    conditions = " ".join(trial_info["conditions"]).upper()
    combined = f"{conditions} {all_text}"
    
    if "MCRC" in combined or "METASTATIC COLORECTAL" in combined or "METASTATIC CRC" in combined:
        return "mCRC"
    if "COLORECTAL" in combined:
        return "Colorectal"
    if "COLON" in combined and "CANCER" in combined:
        return "Colon"
    if "COLON" in combined:
        return "Colon"
    if "RECTAL" in combined:
        return "Rectal"
    if "CRC" in combined:
        return "CRC"
    if "GASTROINTESTINAL" in combined or "GI CANCER" in combined:
        return "GI"
    if "SOLID TUMOR" in combined or "SOLID TUMORS" in combined:
        return "Solid Tumor"
    if "PANCREA" in combined:
        return "Pancreatic"
    if "LUNG" in combined or "NSCLC" in combined:
        return "Lung"
    
    for search in matched_searches:
        if "colorectal" in search.lower():
            return "Colorectal"
        if "colon" in search.lower():
            return "Colon"
        if "crc" in search.lower():
            return "CRC"
    
    return "Other"


# =============================================================================
# PRIORITY ASSIGNMENT
# =============================================================================

def assign_priority(mutation_type: str, cancer_type: str) -> Tuple[int, str]:
    """
    Assign priority tier based on mutation and cancer type.
    """
    is_colorectal = cancer_type in ["mCRC", "Colorectal", "Colon", "Rectal", "CRC"]
    is_g12d = mutation_type == "G12D"
    is_ras_related = mutation_type in ["G12D", "G12C", "G12V", "G12R", "G12A", "G12S", "G12", 
                                        "G13D", "G13", "KRAS", "NRAS", "HRAS", "RAS", 
                                        "Pan-RAS", "RAS(ON)"]
    
    if is_g12d and is_colorectal:
        return (1, "1. G12D, Colon")
    
    if is_g12d or (is_ras_related and is_colorectal):
        return (2, "2. G12D general or RAS + Colon")
    
    if is_colorectal and not is_ras_related:
        return (3, "3. Colon, not RAS")
    
    return (4, "4. Non-colon/non-RAS")


# =============================================================================
# COMPARISON WITH EXISTING DATA
# =============================================================================

def load_existing_trials(filepath: str) -> Set[str]:
    """
    Load existing NCT IDs from the trials spreadsheet.
    """
    try:
        df = pd.read_csv(filepath)
        nct_col = None
        for col in df.columns:
            if 'nct' in col.lower():
                nct_col = col
                break
        
        if nct_col:
            return set(df[nct_col].dropna().unique())
        else:
            print(f"  Warning: Could not find NCT column in {filepath}")
            return set()
    except FileNotFoundError:
        print(f"  Warning: File not found: {filepath}")
        return set()
    except Exception as e:
        print(f"  Warning: Error loading {filepath}: {e}")
        return set()


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_exhaustive_search(resume: bool = True):
    """
    Main function to run the exhaustive search.
    """
    print()
    print("=" * 80)
    print("  EXHAUSTIVE CLINICAL TRIAL SEARCH")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()
    
    # Check for checkpoint
    checkpoint = None
    if resume:
        checkpoint = load_checkpoint()
        if checkpoint:
            print(f"  Found checkpoint from phase: {checkpoint.get('phase', 'unknown')}")
            print(f"  {len(checkpoint.get('all_nct_ids', []))} NCT IDs already collected")
    
    # Phase 1: Run all searches
    search_results = run_all_searches(resume_from=checkpoint)
    
    # Phase 2: Deduplicate
    unique_nct_ids, nct_to_searches = deduplicate_results(search_results)
    
    # Phase 3: Load existing trials for comparison
    print("\n" + "=" * 80)
    print("PHASE 2: Loading existing trials for comparison")
    print("=" * 80)
    
    existing_file = OUTPUT_DIR / "trials_center_level.csv"
    existing_nct_ids = load_existing_trials(str(existing_file))
    print(f"  Loaded {len(existing_nct_ids)} existing trials from spreadsheet")
    
    # Phase 4: Fetch details and categorize each trial
    print("\n" + "=" * 80)
    print("PHASE 3: Fetching trial details and categorizing")
    print("=" * 80)
    
    trials_data = []
    total = len(unique_nct_ids)
    failed_fetches = []
    
    for i, nct_id in enumerate(sorted(unique_nct_ids), 1):
        if i % 25 == 0 or i == 1 or i == total:
            print(f"  Processing {i}/{total}... ({len(trials_data)} successful)")
            # Save incremental progress
            if trials_data:
                temp_df = pd.DataFrame(trials_data)
                temp_df.to_csv(OUTPUT_DIR / "exhaustive_search_partial.csv", index=False)
        
        # Fetch trial details
        study_data = fetch_trial_details(nct_id)
        if not study_data:
            failed_fetches.append(nct_id)
            continue
        
        # Extract info
        trial_info = extract_trial_info(study_data)
        matched_searches = nct_to_searches.get(nct_id, [])
        
        # Categorize
        mutation_type = detect_mutation_type(trial_info, matched_searches)
        cancer_type = detect_cancer_type(trial_info, matched_searches)
        
        # Assign priority
        priority_num, priority_desc = assign_priority(mutation_type, cancer_type)
        
        # Check if already in list
        already_in_list = nct_id in existing_nct_ids
        
        # Build row
        trials_data.append({
            "NCT Code": nct_id,
            "Trial Name": trial_info["title"],
            "Trial URL": f"https://clinicaltrials.gov/study/{nct_id}",
            "Priority": priority_desc,
            "Priority Num": priority_num,
            "Status": trial_info["status"],
            "Already In List": already_in_list,
            "Mutation Type": mutation_type,
            "Cancer Type": cancer_type,
            "Interventions": "; ".join(trial_info["interventions"][:5]),
            "Sponsor": trial_info["sponsor"],
        })
        
        time.sleep(0.3)  # Rate limiting
    
    # Phase 5: Create DataFrame and sort
    print("\n" + "=" * 80)
    print("PHASE 4: Creating final output")
    print("=" * 80)
    
    df = pd.DataFrame(trials_data)
    
    # Sort by priority, then by already_in_list (False first = new trials first)
    df = df.sort_values(["Priority Num", "Already In List", "NCT Code"])
    df = df.drop(columns=["Priority Num"])
    
    # Save to CSV
    output_file = OUTPUT_DIR / "exhaustive_search_results.csv"
    df.to_csv(output_file, index=False)
    
    # Remove partial file if it exists
    partial_file = OUTPUT_DIR / "exhaustive_search_partial.csv"
    if partial_file.exists():
        partial_file.unlink()
    
    # Print summary
    print(f"\n  Total unique trials found: {len(df)}")
    print(f"  Already in your list: {df['Already In List'].sum()}")
    print(f"  NEW trials: {(~df['Already In List']).sum()}")
    
    if failed_fetches:
        print(f"  Failed to fetch: {len(failed_fetches)} trials")
    
    print()
    print("  By Priority Tier:")
    for priority in sorted(df["Priority"].unique()):
        count = len(df[df["Priority"] == priority])
        new_count = len(df[(df["Priority"] == priority) & (~df["Already In List"])])
        print(f"    {priority}: {count} total ({new_count} new)")
    
    print()
    print("  By Mutation Type:")
    for mut in df["Mutation Type"].value_counts().head(10).index:
        count = df["Mutation Type"].value_counts()[mut]
        print(f"    {mut}: {count}")
    
    print()
    print("  By Cancer Type:")
    for cancer in df["Cancer Type"].value_counts().head(10).index:
        count = df["Cancer Type"].value_counts()[cancer]
        print(f"    {cancer}: {count}")
    
    print()
    print(f"  Results saved to: {output_file}")
    print(f"  Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    return df


if __name__ == "__main__":
    df = run_exhaustive_search(resume=True)
