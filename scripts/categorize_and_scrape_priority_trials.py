"""
Categorize + Scrape Priority (Tier 2) Trials
- Categorize with GPT-5.2
- Scrape centers for each trial
- Add geographic flags (in_usa, in_california, is_local)
- Export both trial-level and center-level CSVs
"""

import os
import json
import time
import requests
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
import sys
sys.path.insert(0, '..')

from prompts.trial_categorization import get_trial_categorization_prompt
from utils.location_utils import is_local_zip

load_dotenv('../.env')
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

# Reference zip for SoCal
SOCAL_ZIP = '91765'


def fetch_trial_data(nct_id):
    """Fetch comprehensive trial data from API."""
    url = f'https://clinicaltrials.gov/api/v2/studies/{nct_id}'
    data = requests.get(url, params={'format': 'json'}, timeout=30).json()
    protocol = data.get('protocolSection', {})
    
    return {
        'protocol': protocol,
        'title': protocol.get('identificationModule', {}).get('briefTitle', ''),
        'official_title': protocol.get('identificationModule', {}).get('officialTitle', ''),
        'conditions': protocol.get('conditionsModule', {}).get('conditions', []),
        'interventions': [i.get('name', '') for i in protocol.get('armsInterventionsModule', {}).get('interventions', [])],
        'brief_summary': protocol.get('descriptionModule', {}).get('briefSummary', ''),
        'eligibility': protocol.get('eligibilityModule', {}).get('eligibilityCriteria', ''),
        'phase': protocol.get('designModule', {}).get('phases', []),
        'status': protocol.get('statusModule', {}).get('overallStatus', ''),
    }


def categorize_trial_gpt52(nct_id, trial_data):
    """Categorize trial with GPT-5.2."""
    prompt = get_trial_categorization_prompt(
        nct_id,
        trial_data['title'],
        trial_data['official_title'],
        trial_data['conditions'],
        trial_data['interventions'],
        trial_data['brief_summary'],
        trial_data['eligibility']
    )
    
    json_prompt = prompt + "\n\nRespond with ONLY valid JSON in the exact format specified above."
    
    response = client.responses.create(
        model='gpt-5.2',
        input=json_prompt,
    )
    
    # Extract text
    text = None
    for item in response.output:
        if hasattr(item, 'type') and item.type == 'message':
            if hasattr(item, 'content') and len(item.content) > 0:
                text = item.content[0].text
                break
    
    if not text:
        return None
    
    return json.loads(text)


def scrape_centers(nct_id, protocol):
    """Scrape centers and contacts from API."""
    contacts_module = protocol.get('contactsLocationsModule', {})
    locations = contacts_module.get('locations', [])
    
    if not locations:
        return []
    
    centers = []
    for loc in locations:
        facility = loc.get('facility', '')
        city = loc.get('city', '')
        state = loc.get('state', '')
        zip_code = loc.get('zip', '')
        country = loc.get('country', '')
        
        # Geographic flags
        in_usa = (country == 'United States')
        in_california = (in_usa and state == 'California')
        is_local = False
        
        if in_california and zip_code:
            try:
                is_local = is_local_zip(zip_code, SOCAL_ZIP, max_distance=150)
            except:
                is_local = False
        
        # Extract contacts
        contacts = loc.get('contacts', [])
        
        center_data = {
            'nct_id': nct_id,
            'facility': facility,
            'city': city,
            'state': state,
            'zip': zip_code,
            'country': country,
            'in_usa': in_usa,
            'in_california': in_california,
            'is_local': is_local,
        }
        
        # Add primary contact
        if contacts and len(contacts) > 0:
            primary = contacts[0]
            center_data['contact_name'] = primary.get('name', '')
            center_data['contact_phone'] = primary.get('phone', '')
            center_data['contact_email'] = primary.get('email', '')
        
        # Add backup contact
        if contacts and len(contacts) > 1:
            backup = contacts[1]
            center_data['contact_2_name'] = backup.get('name', '')
            center_data['contact_2_phone'] = backup.get('phone', '')
            center_data['contact_2_email'] = backup.get('email', '')
        
        centers.append(center_data)
    
    # Get study-level contacts
    central_contacts = contacts_module.get('centralContacts', [])
    study_contact = central_contacts[0] if len(central_contacts) > 0 else {}
    study_backup = central_contacts[1] if len(central_contacts) > 1 else {}
    
    # Add study contacts to each center
    for center in centers:
        center['study_contact_name'] = study_contact.get('name', '')
        center['study_contact_phone'] = study_contact.get('phone', '')
        center['study_contact_email'] = study_contact.get('email', '')
        center['study_backup_name'] = study_backup.get('name', '')
        center['study_backup_phone'] = study_backup.get('phone', '')
        center['study_backup_email'] = study_backup.get('email', '')
    
    return centers


def process_trial(nct_id, trial_metadata):
    """Process a single trial: categorize + scrape centers."""
    print(f"\n{nct_id}: ", end='', flush=True)
    
    try:
        # Fetch data
        trial_data = fetch_trial_data(nct_id)
        
        # Categorize with GPT-5.2
        print("categorizing...", end='', flush=True)
        categorization = categorize_trial_gpt52(nct_id, trial_data)
        
        if not categorization:
            print(" ERROR: categorization failed")
            return None, []
        
        tier = categorization.get('classification', {}).get('tier', '?')
        print(f" Tier {tier}", end='', flush=True)
        
        # Scrape centers
        print(", scraping centers...", end='', flush=True)
        centers = scrape_centers(nct_id, trial_data['protocol'])
        print(f" {len(centers)} centers", end='', flush=True)
        
        # Calculate study-level flags
        has_usa_center = any(c['in_usa'] for c in centers)
        has_california_center = any(c['in_california'] for c in centers)
        has_local_center = any(c['is_local'] for c in centers)
        num_centers = len(centers)
        num_local_centers = sum(1 for c in centers if c['is_local'])
        
        # Build trial-level result
        trial_result = {
            'nct_id': nct_id,
            'trial_name': trial_data['title'],
            'trial_url': f"https://clinicaltrials.gov/study/{nct_id}",
            'tier': tier,
            'tier_reason': categorization.get('classification', {}).get('tier_reason', ''),
            'mutation_type': categorization.get('analysis', {}).get('explicit_mutation_requirement', ''),
            'cancer_scope': categorization.get('classification', {}).get('cancer_scope', ''),
            'phase': ', '.join(trial_data['phase']) if trial_data['phase'] else '',
            'status': trial_data['status'],
            'has_usa_center': has_usa_center,
            'has_california_center': has_california_center,
            'has_local_center': has_local_center,
            'num_centers': num_centers,
            'num_local_centers': num_local_centers,
        }
        
        print(" ✓")
        return trial_result, centers
        
    except Exception as e:
        print(f" ERROR: {str(e)[:50]}")
        return None, []


def main():
    """Process all priority trials."""
    print("="*80)
    print("CATEGORIZE + SCRAPE PRIORITY (TIER 2) TRIALS")
    print("Using GPT-5.2 for categorization")
    print("="*80)
    
    # Load trial list
    trials_df = pd.read_csv('../data/priority_trials.csv')
    
    print(f"\nProcessing {len(trials_df)} priority trials")
    print(f"Output: trial-level + center-level CSVs with geographic flags")
    
    trial_results = []
    all_centers = []
    
    for idx, row in trials_df.iterrows():
        nct_id = row['NCT Code']
        
        trial_result, centers = process_trial(nct_id, row)
        
        if trial_result:
            trial_results.append(trial_result)
            all_centers.extend(centers)
        
        # Save periodically
        if len(trial_results) % 10 == 0:
            pd.DataFrame(trial_results).to_csv('../output/priority_trials_categorized_partial.csv', index=False)
            pd.DataFrame(all_centers).to_csv('../output/priority_centers_partial.csv', index=False)
            print(f"\n  Progress: {len(trial_results)}/{len(trials_df)} trials processed")
    
    # Final save
    trials_df_out = pd.DataFrame(trial_results)
    centers_df_out = pd.DataFrame(all_centers)
    
    trials_df_out.to_csv('../output/priority_trials_categorized.csv', index=False)
    centers_df_out.to_csv('../output/priority_centers.csv', index=False)
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    print(f"\nProcessed {len(trial_results)} trials")
    print(f"Scraped {len(all_centers)} centers")
    
    print(f"\nTier distribution:")
    print(trials_df_out['tier'].value_counts().sort_index())
    
    print(f"\nGeographic distribution (trial-level):")
    print(f"  Has USA center: {trials_df_out['has_usa_center'].sum()} ({trials_df_out['has_usa_center'].sum()/len(trials_df_out)*100:.1f}%)")
    print(f"  Has CA center: {trials_df_out['has_california_center'].sum()} ({trials_df_out['has_california_center'].sum()/len(trials_df_out)*100:.1f}%)")
    print(f"  Has local center: {trials_df_out['has_local_center'].sum()} ({trials_df_out['has_local_center'].sum()/len(trials_df_out)*100:.1f}%)")
    
    print(f"\nGeographic distribution (center-level):")
    print(f"  USA centers: {centers_df_out['in_usa'].sum()} ({centers_df_out['in_usa'].sum()/len(centers_df_out)*100:.1f}%)")
    print(f"  CA centers: {centers_df_out['in_california'].sum()} ({centers_df_out['in_california'].sum()/len(centers_df_out)*100:.1f}%)")
    print(f"  Local centers: {centers_df_out['is_local'].sum()} ({centers_df_out['is_local'].sum()/len(centers_df_out)*100:.1f}%)")
    
    print(f"\nOutput saved to:")
    print(f"  output/priority_trials_categorized.csv (trial-level)")
    print(f"  output/priority_centers.csv (center-level)")


if __name__ == '__main__':
    main()

