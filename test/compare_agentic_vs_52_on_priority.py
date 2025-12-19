"""
Compare Agentic GPT-5-mini vs GPT-5.2 on the 330 priority trials.
Goal: Measure real-world accuracy of the agentic system on diverse trials.
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
    """Compare agentic 5-mini vs 5.2 on priority trials."""
    print("="*80)
    print("COMPARING AGENTIC GPT-5-MINI VS GPT-5.2 ON PRIORITY TRIALS")
    print("="*80)
    
    # Load GPT-5.2 results (ground truth)
    gpt52_df = pd.read_csv('../output/priority_trials_categorized.csv')
    
    print(f"\nLoaded {len(gpt52_df)} trials categorized by GPT-5.2")
    print("\nGPT-5.2 Tier Distribution:")
    print(gpt52_df['tier'].value_counts().sort_index())
    
    # Test on a sample first (let's do 50 trials to start)
    sample_size = 50
    print(f"\n" + "="*80)
    print(f"TESTING ON RANDOM SAMPLE OF {sample_size} TRIALS")
    print("="*80)
    
    # Stratified sample (proportional from each tier)
    sample_df = gpt52_df.groupby('tier', group_keys=False).apply(
        lambda x: x.sample(min(len(x), int(sample_size * len(x) / len(gpt52_df)) + 1), random_state=42)
    ).head(sample_size)
    
    print(f"\nSample tier distribution:")
    print(sample_df['tier'].value_counts().sort_index())
    
    results = []
    total_cost_agentic = 0
    total_cost_gpt52 = 0
    
    for idx, row in sample_df.iterrows():
        nct_id = row['nct_id']
        gpt52_tier = float(row['tier'])
        
        print(f"\n{nct_id} (GPT-5.2: Tier {gpt52_tier})", end='', flush=True)
        
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
            
            agentic_tier = float(result['classification']['tier'])
            verification = result.get('_verification', {})
            
            # Calculate cost
            cost_info = calculate_cost(result)
            total_cost_agentic += cost_info['agentic_mini_cost']
            total_cost_gpt52 += cost_info['gpt_5_2_cost']
            
            # Check match
            match = abs(agentic_tier - gpt52_tier) < 0.01
            match_symbol = '✓' if match else '✗'
            
            print(f" → Agentic: Tier {agentic_tier} {match_symbol}", end='')
            
            if verification.get('corrected'):
                print(f" [CORRECTED]", end='')
            
            print()
            
            results.append({
                'nct_id': nct_id,
                'gpt_5_2_tier': gpt52_tier,
                'agentic_tier': agentic_tier,
                'match': match,
                'corrected': verification.get('corrected', False),
                'verification_performed': verification.get('performed', False),
                'mutation_5_2': row['mutation_type'],
                'cancer_scope_5_2': row['cancer_scope'],
                'mutation_agentic': result['analysis'].get('explicit_mutation_requirement', ''),
                'cancer_scope_agentic': result['classification'].get('cancer_scope', ''),
            })
            
        except Exception as e:
            print(f" ERROR: {str(e)[:50]}")
            continue
        
        # Save partial results every 10
        if len(results) % 10 == 0:
            pd.DataFrame(results).to_csv('agentic_vs_52_partial.csv', index=False)
            print(f"  Progress: {len(results)}/{sample_size} completed")
    
    # Final analysis
    results_df = pd.DataFrame(results)
    results_df.to_csv('agentic_vs_52_comparison.csv', index=False)
    
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)
    
    # Overall accuracy
    accuracy = (results_df['match'].sum() / len(results_df)) * 100
    print(f"\nOverall Accuracy: {results_df['match'].sum()}/{len(results_df)} ({accuracy:.1f}%)")
    
    # Accuracy by tier
    print(f"\nAccuracy by GPT-5.2 tier:")
    for tier in sorted(results_df['gpt_5_2_tier'].unique()):
        tier_df = results_df[results_df['gpt_5_2_tier'] == tier]
        tier_accuracy = (tier_df['match'].sum() / len(tier_df)) * 100
        print(f"  Tier {tier}: {tier_df['match'].sum()}/{len(tier_df)} ({tier_accuracy:.1f}%)")
    
    # Verification stats
    verifications = results_df['verification_performed'].sum()
    corrections = results_df['corrected'].sum()
    print(f"\nVerification:")
    print(f"  Edge cases detected: {verifications}/{len(results_df)}")
    print(f"  Corrections made: {corrections}/{len(results_df)}")
    
    # Disagreement analysis
    disagreements = results_df[~results_df['match']]
    if len(disagreements) > 0:
        print(f"\n" + "="*80)
        print(f"DISAGREEMENTS ({len(disagreements)} cases):")
        print("="*80)
        for idx, row in disagreements.head(10).iterrows():
            print(f"\n{row['nct_id']}")
            print(f"  GPT-5.2:  Tier {row['gpt_5_2_tier']} | {row['mutation_5_2']} + {row['cancer_scope_5_2']}")
            print(f"  Agentic:  Tier {row['agentic_tier']} | {row['mutation_agentic']} + {row['cancer_scope_agentic']}")
    
    # Cost comparison
    print(f"\n" + "="*80)
    print("COST COMPARISON")
    print("="*80)
    print(f"\nFor {len(results_df)} trials:")
    print(f"  Agentic GPT-5-mini: ${total_cost_agentic:.4f}")
    print(f"  GPT-5.2 alone:      ${total_cost_gpt52:.4f}")
    print(f"  Savings:            ${total_cost_gpt52 - total_cost_agentic:.4f} ({(1 - total_cost_agentic/total_cost_gpt52)*100:.1f}%)")
    
    # Extrapolate to 330
    cost_330_agentic = (total_cost_agentic / len(results_df)) * 330
    cost_330_gpt52 = (total_cost_gpt52 / len(results_df)) * 330
    
    print(f"\nExtrapolated to all 330 priority trials:")
    print(f"  Agentic GPT-5-mini: ${cost_330_agentic:.2f}")
    print(f"  GPT-5.2 alone:      ${cost_330_gpt52:.2f}")
    print(f"  Savings:            ${cost_330_gpt52 - cost_330_agentic:.2f}")
    
    print(f"\n" + "="*80)
    print(f"Results saved to: agentic_vs_52_comparison.csv")
    print("="*80)


if __name__ == '__main__':
    main()

