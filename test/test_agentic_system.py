"""
Test the agentic two-pass system on the 17 disagreement cases.
Goal: Get GPT-5-mini + agentic chain to match GPT-5.2's accuracy.
"""

import os
import json
import time
import requests
import pandas as pd
from dotenv import load_dotenv
import sys
sys.path.insert(0, '..')

from gpt.agentic_categorizer import categorize_with_agentic_chain, calculate_cost

load_dotenv('../.env')


def fetch_trial_data(nct_id):
    """Fetch trial data from API."""
    url = f'https://clinicaltrials.gov/api/v2/studies/{nct_id}'
    data = requests.get(url, params={'format': 'json'}, timeout=30).json()
    protocol = data.get('protocolSection', {})
    
    return {
        'title': protocol.get('identificationModule', {}).get('briefTitle', ''),
        'official_title': protocol.get('identificationModule', {}).get('officialTitle', ''),
        'conditions': protocol.get('conditionsModule', {}).get('conditions', []),
        'interventions': [i.get('name', '') for i in protocol.get('armsInterventionsModule', {}).get('interventions', [])],
        'brief_summary': protocol.get('descriptionModule', {}).get('briefSummary', ''),
        'eligibility': protocol.get('eligibilityModule', {}).get('eligibilityCriteria', ''),
    }


def main():
    """Test agentic system on the 17 disagreements."""
    print("="*80)
    print("TESTING AGENTIC TWO-PASS SYSTEM")
    print("="*80)
    
    # Load the disagreements
    df = pd.read_csv('tier_3_4_recat_results.csv')
    df['gpt_5_2_tier'] = df['gpt_5_2_tier'].astype(str)
    df['gpt_5_mini_tier'] = df['gpt_5_mini_tier'].astype(str)
    
    disagreements = df[
        (df['gpt_5_mini_tier'] == '2') & 
        (df['gpt_5_2_tier'].isin(['3', '4']))
    ]
    
    print(f"\nTesting on {len(disagreements)} disagreement cases")
    print(f"Goal: Match GPT-5.2's Tier 3/4 classification\n")
    
    results = []
    total_cost_agentic = 0
    total_cost_gpt52 = 0
    corrections_made = 0
    
    for idx, row in disagreements.head(10).iterrows():  # Test first 10
        nct_id = row['nct_id']
        original_tier = row['original_tier']
        gpt52_tier = row['gpt_5_2_tier']
        mini_tier = row['gpt_5_mini_tier']
        
        print(f"{nct_id} (Original: T{original_tier}, 5.2: T{gpt52_tier}, 5-mini: T{mini_tier})")
        
        try:
            # Fetch data
            trial_data = fetch_trial_data(nct_id)
            
            # Run agentic categorization
            result = categorize_with_agentic_chain(
                nct_id,
                trial_data['title'],
                trial_data['official_title'],
                trial_data['conditions'],
                trial_data['interventions'],
                trial_data['brief_summary'],
                trial_data['eligibility']
            )
            
            agentic_tier = str(result['classification']['tier'])
            verification = result.get('_verification', {})
            
            # Calculate cost
            cost_info = calculate_cost(result)
            total_cost_agentic += cost_info['agentic_mini_cost']
            total_cost_gpt52 += cost_info['gpt_5_2_cost']
            
            # Check if corrected
            if verification.get('corrected'):
                corrections_made += 1
                print(f"  ✓ Agentic: T{agentic_tier} (CORRECTED from original)")
            else:
                print(f"  → Agentic: T{agentic_tier}")
            
            # Check if matches GPT-5.2
            match = '✓' if agentic_tier == gpt52_tier else '✗'
            print(f"  Match GPT-5.2: {match}")
            
            if verification.get('performed'):
                print(f"  Verification: {verification.get('notes', '')[:60]}")
            
            results.append({
                'nct_id': nct_id,
                'original_tier': original_tier,
                'gpt_5_2_tier': gpt52_tier,
                'gpt_5_mini_tier': mini_tier,
                'agentic_tier': agentic_tier,
                'corrected': verification.get('corrected', False),
                'matches_gpt52': agentic_tier == gpt52_tier,
                'cost_agentic': cost_info['agentic_mini_cost'],
                'cost_gpt52': cost_info['gpt_5_2_cost'],
            })
            
            print()
            
        except Exception as e:
            print(f"  ERROR: {str(e)[:60]}\n")
            continue
    
    # Summary
    results_df = pd.DataFrame(results)
    
    print("="*80)
    print("SUMMARY")
    print("="*80)
    
    accuracy = (results_df['matches_gpt52'].sum() / len(results_df)) * 100
    print(f"\nAccuracy (matching GPT-5.2): {results_df['matches_gpt52'].sum()}/{len(results_df)} ({accuracy:.1f}%)")
    print(f"Corrections made by verification: {corrections_made}/{len(results_df)}")
    
    print(f"\nCost comparison (for {len(results_df)} trials):")
    print(f"  Agentic GPT-5-mini: ${total_cost_agentic:.4f}")
    print(f"  GPT-5.2 alone:      ${total_cost_gpt52:.4f}")
    print(f"  Savings:            ${total_cost_gpt52 - total_cost_agentic:.4f} ({(1 - total_cost_agentic/total_cost_gpt52)*100:.1f}%)")
    
    # Extrapolate to 5000 trials
    cost_5k_agentic = (total_cost_agentic / len(results_df)) * 5000
    cost_5k_gpt52 = (total_cost_gpt52 / len(results_df)) * 5000
    
    print(f"\nExtrapolated to 5,000 trials:")
    print(f"  Agentic GPT-5-mini: ${cost_5k_agentic:.2f}")
    print(f"  GPT-5.2 alone:      ${cost_5k_gpt52:.2f}")
    print(f"  Savings:            ${cost_5k_gpt52 - cost_5k_agentic:.2f}")
    
    results_df.to_csv('agentic_system_test_results.csv', index=False)
    print(f"\nResults saved to: agentic_system_test_results.csv")


if __name__ == '__main__':
    main()

