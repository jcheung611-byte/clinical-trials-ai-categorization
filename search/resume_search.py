#!/usr/bin/env python3
"""
Resume exhaustive search from checkpoint.
Picks up where we left off fetching trial details.
"""

import requests
import json
import re
import time
import pandas as pd
from typing import Optional, Dict, List, Set
from pathlib import Path
from datetime import datetime


BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
SCRIPT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = SCRIPT_DIR / "output"


def fetch_trial_details(nct_id: str, max_retries: int = 3) -> Optional[Dict]:
    """Fetch trial details with retry logic."""
    url = f"{BASE_URL}/{nct_id}"
    params = {"format": "json"}
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(1.5 * (attempt + 1))  # Exponential backoff
            else:
                return None
    return None


def extract_trial_info(study_data: Dict) -> Dict:
    """Extract relevant fields from API response."""
    protocol = study_data.get("protocolSection", {})
    
    id_module = protocol.get("identificationModule", {})
    nct_id = id_module.get("nctId", "")
    title = id_module.get("briefTitle", "")
    
    status_module = protocol.get("statusModule", {})
    overall_status = status_module.get("overallStatus", "")
    
    conditions_module = protocol.get("conditionsModule", {})
    conditions = conditions_module.get("conditions", [])
    
    arms_module = protocol.get("armsInterventionsModule", {})
    interventions = arms_module.get("interventions", [])
    intervention_names = [i.get("name", "") for i in interventions]
    
    sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
    lead_sponsor = sponsor_module.get("leadSponsor", {})
    sponsor_name = lead_sponsor.get("name", "")
    
    eligibility_module = protocol.get("eligibilityModule", {})
    eligibility_text = eligibility_module.get("eligibilityCriteria", "")
    
    description_module = protocol.get("descriptionModule", {})
    brief_summary = description_module.get("briefSummary", "")
    
    return {
        "nct_id": nct_id,
        "title": title,
        "status": overall_status,
        "conditions": conditions,
        "interventions": intervention_names,
        "sponsor": sponsor_name,
        "all_text": f"{title} {' '.join(conditions)} {eligibility_text} {brief_summary}".upper()
    }


def detect_mutation_type(trial_info: Dict) -> str:
    """Determine mutation type from trial text."""
    all_text = trial_info["all_text"]
    
    if "G12D" in all_text:
        return "G12D"
    if "G12C" in all_text:
        return "G12C"
    if "G12V" in all_text:
        return "G12V"
    if "G12R" in all_text:
        return "G12R"
    if re.search(r"\bG12\b", all_text):
        return "G12"
    if "G13D" in all_text:
        return "G13D"
    if re.search(r"\bG13\b", all_text):
        return "G13"
    if "PAN-RAS" in all_text or "PAN RAS" in all_text:
        return "Pan-RAS"
    if "RAS(ON)" in all_text:
        return "RAS(ON)"
    if "KRAS" in all_text:
        return "KRAS"
    if "NRAS" in all_text:
        return "NRAS"
    if "HRAS" in all_text:
        return "HRAS"
    if re.search(r"\bRAS\b", all_text):
        return "RAS"
    return "None"


def detect_cancer_type(trial_info: Dict) -> str:
    """Determine cancer type from trial text."""
    all_text = trial_info["all_text"]
    conditions = " ".join(trial_info["conditions"]).upper()
    combined = f"{conditions} {all_text}"
    
    if "MCRC" in combined or "METASTATIC COLORECTAL" in combined:
        return "mCRC"
    if "COLORECTAL" in combined:
        return "Colorectal"
    if "COLON" in combined:
        return "Colon"
    if "RECTAL" in combined:
        return "Rectal"
    if "CRC" in combined:
        return "CRC"
    if "GASTROINTESTINAL" in combined:
        return "GI"
    if "SOLID TUMOR" in combined:
        return "Solid Tumor"
    if "PANCREA" in combined:
        return "Pancreatic"
    if "LUNG" in combined or "NSCLC" in combined:
        return "Lung"
    return "Other"


def assign_priority(mutation_type: str, cancer_type: str) -> tuple:
    """Assign priority tier."""
    is_colorectal = cancer_type in ["mCRC", "Colorectal", "Colon", "Rectal", "CRC"]
    is_g12d = mutation_type == "G12D"
    is_ras = mutation_type in ["G12D", "G12C", "G12V", "G12R", "G12", "G13D", "G13", 
                               "KRAS", "NRAS", "HRAS", "RAS", "Pan-RAS", "RAS(ON)"]
    
    if is_g12d and is_colorectal:
        return (1, "1. G12D, Colon")
    if is_g12d or (is_ras and is_colorectal):
        return (2, "2. G12D general or RAS + Colon")
    if is_colorectal and not is_ras:
        return (3, "3. Colon, not RAS")
    return (4, "4. Non-colon/non-RAS")


def load_existing_trials() -> Set[str]:
    """Load existing NCT IDs from spreadsheet."""
    filepath = OUTPUT_DIR / "trials_center_level.csv"
    try:
        df = pd.read_csv(filepath)
        for col in df.columns:
            if 'nct' in col.lower():
                return set(df[col].dropna().unique())
    except:
        pass
    return set()


def load_already_processed() -> Set[str]:
    """Load NCT IDs that were already processed."""
    filepath = OUTPUT_DIR / "exhaustive_search_partial.csv"
    try:
        df = pd.read_csv(filepath)
        return set(df["NCT Code"].dropna().unique())
    except:
        pass
    return set()


def resume_from_checkpoint():
    """Resume fetching trial details from checkpoint."""
    print()
    print("=" * 70)
    print("  RESUMING EXHAUSTIVE SEARCH FROM CHECKPOINT")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Load checkpoint
    checkpoint_file = OUTPUT_DIR / "search_checkpoint.json"
    if not checkpoint_file.exists():
        print("ERROR: No checkpoint file found. Run full search first.")
        return
    
    with open(checkpoint_file) as f:
        checkpoint = json.load(f)
    
    all_nct_ids = set(checkpoint["all_nct_ids"])
    print(f"\n  Total NCT IDs in checkpoint: {len(all_nct_ids)}")
    
    # Load already processed
    already_processed = load_already_processed()
    print(f"  Already processed: {len(already_processed)}")
    
    # Find remaining
    remaining = all_nct_ids - already_processed
    print(f"  Remaining to process: {len(remaining)}")
    
    if not remaining:
        print("\n  All trials already processed!")
        return
    
    # Load existing trials for comparison
    existing_nct_ids = load_existing_trials()
    print(f"  Existing trials in your list: {len(existing_nct_ids)}")
    
    # Load existing partial results
    partial_file = OUTPUT_DIR / "exhaustive_search_partial.csv"
    if partial_file.exists():
        existing_df = pd.read_csv(partial_file)
        trials_data = existing_df.to_dict('records')
    else:
        trials_data = []
    
    # Process remaining trials
    print(f"\n  Processing {len(remaining)} remaining trials...")
    print("  (Saving every 100 trials)")
    print()
    
    remaining_list = sorted(remaining)
    total = len(remaining_list)
    processed = 0
    errors = 0
    
    for i, nct_id in enumerate(remaining_list, 1):
        # Progress update
        if i % 50 == 0 or i == 1:
            print(f"  [{i}/{total}] Processing... (errors: {errors})")
        
        # Fetch with retry
        study_data = fetch_trial_details(nct_id)
        if not study_data:
            errors += 1
            continue
        
        # Process
        trial_info = extract_trial_info(study_data)
        mutation_type = detect_mutation_type(trial_info)
        cancer_type = detect_cancer_type(trial_info)
        priority_num, priority_desc = assign_priority(mutation_type, cancer_type)
        
        trials_data.append({
            "NCT Code": nct_id,
            "Trial Name": trial_info["title"],
            "Trial URL": f"https://clinicaltrials.gov/study/{nct_id}",
            "Priority": priority_desc,
            "Priority Num": priority_num,
            "Status": trial_info["status"],
            "Already In List": nct_id in existing_nct_ids,
            "Mutation Type": mutation_type,
            "Cancer Type": cancer_type,
            "Interventions": "; ".join(trial_info["interventions"][:5]),
            "Sponsor": trial_info["sponsor"],
        })
        
        processed += 1
        
        # Save checkpoint every 100 trials
        if processed % 100 == 0:
            df = pd.DataFrame(trials_data)
            df = df.sort_values(["Priority Num", "Already In List", "NCT Code"])
            df.to_csv(partial_file, index=False)
            print(f"  [Checkpoint saved: {len(df)} trials]")
        
        # Rate limiting
        time.sleep(0.15)
    
    # Final save
    df = pd.DataFrame(trials_data)
    df = df.sort_values(["Priority Num", "Already In List", "NCT Code"])
    df = df.drop(columns=["Priority Num"])
    
    # Save final results
    final_file = OUTPUT_DIR / "exhaustive_search_results.csv"
    df.to_csv(final_file, index=False)
    
    # Also update partial file
    df_with_num = pd.DataFrame(trials_data)
    df_with_num = df_with_num.sort_values(["Priority Num", "Already In List", "NCT Code"])
    df_with_num.to_csv(partial_file, index=False)
    
    # Summary
    print()
    print("=" * 70)
    print("  COMPLETE!")
    print("=" * 70)
    print(f"\n  Total trials: {len(df)}")
    print(f"  Already in your list: {df['Already In List'].sum()}")
    print(f"  NEW trials: {(~df['Already In List']).sum()}")
    print(f"  Errors (could not fetch): {errors}")
    print()
    print("  By Priority:")
    for p in sorted(df["Priority"].unique()):
        count = len(df[df["Priority"] == p])
        new = len(df[(df["Priority"] == p) & (~df["Already In List"])])
        print(f"    {p}: {count} total ({new} new)")
    print()
    print(f"  Results saved to: {final_file}")


if __name__ == "__main__":
    resume_from_checkpoint()

