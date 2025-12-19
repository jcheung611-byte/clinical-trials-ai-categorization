"""
Hybrid Categorization Pipeline
- Step 1: Run agentic 5-mini on ALL trials (fast, cheap)
- Step 2: Filter Tier 1/1.5/2 results
- Step 3: Re-categorize Tier 1/1.5/2 with GPT-5.2 (accurate)
- Step 4: Merge results (5.2 for T1/T2, agentic for T3/T4)

This provides 60% cost savings while maintaining high accuracy on priority trials.
"""

import os
import sys
import json
import time
import requests
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

sys.path.insert(0, '..')
from gpt.agentic_categorizer import categorize_with_agentic_chain, calculate_cost
from prompts.trial_categorization import get_trial_categorization_prompt

load_dotenv('../.env')
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))


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
        'phase': protocol.get('designModule', {}).get('phases', []),
        'status': protocol.get('statusModule', {}).get('overallStatus', ''),
    }


def categorize_with_gpt52(nct_id, trial_data):
    """Categorize with GPT-5.2 (for verification)."""
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
        raise ValueError("Could not extract response")
    
    result = json.loads(text)
    
    # Add usage stats
    result['_meta'] = {
        'model': 'gpt-5.2',
        'input_tokens': response.usage.input_tokens,
        'output_tokens': response.usage.output_tokens,
    }
    
    return result


def main():
    """Run the hybrid categorization pipeline."""
    print("="*80)
    print("HYBRID CATEGORIZATION PIPELINE")
    print("="*80)
    
    # Load trial list (from previous exhaustive search)
    trials_df = pd.read_csv('../output/exhaustive_search_results_v2.csv')
    # Standardize column name
    trials_df.rename(columns={'NCT Code': 'nct_id'}, inplace=True)
    print(f"\nLoaded {len(trials_df)} trials from exhaustive search")
    
    # Load existing 330 GPT-5.2 results (SKIP THESE - already categorized!)
    existing_330 = pd.read_csv('../output/priority_trials_categorized.csv')
    existing_ncts = set(existing_330['nct_id'].values)
    print(f"Found {len(existing_ncts)} trials already categorized by GPT-5.2")
    
    # Filter to only new trials
    trials_df = trials_df[~trials_df['nct_id'].isin(existing_ncts)]
    print(f"Will process {len(trials_df)} NEW trials (skipping 330 already done)")
    
    # =========================================================================
    # STEP 1: Run agentic 5-mini on ALL trials
    # =========================================================================
    print("\n" + "="*80)
    print("STEP 1: AGENTIC 5-MINI CATEGORIZATION (ALL TRIALS)")
    print("="*80)
    
    agentic_results = []
    total_cost_agentic = 0
    start_time = time.time()
    
    # Check for checkpoint
    checkpoint_file = '../output/agentic_checkpoint.csv'
    if os.path.exists(checkpoint_file):
        existing = pd.read_csv(checkpoint_file)
        agentic_results = existing.to_dict('records')
        print(f"\n✓ Resuming from checkpoint: {len(agentic_results)} trials completed")
    
    for idx, row in trials_df.iterrows():
        # Skip if already processed
        if any(r['nct_id'] == row['nct_id'] for r in agentic_results):
            continue
        
        nct_id = row['nct_id']
        
        try:
            # Fetch data
            trial_data = fetch_trial_data(nct_id)
            
            # Categorize with agentic
            result = categorize_with_agentic_chain(
                nct_id,
                trial_data['title'],
                trial_data['official_title'],
                trial_data['conditions'],
                trial_data['interventions'],
                trial_data['brief_summary'],
                trial_data['eligibility']
            )
            
            # Calculate cost
            cost_info = calculate_cost(result)
            total_cost_agentic += cost_info['agentic_mini_cost']
            
            # Extract key fields
            agentic_results.append({
                'nct_id': nct_id,
                'trial_name': trial_data['title'],
                'agentic_tier': result['classification']['tier'],
                'agentic_mutation': result['analysis'].get('explicit_mutation_requirement', ''),
                'agentic_cancer_scope': result['classification'].get('cancer_scope', ''),
                'agentic_tier_reason': result['classification'].get('tier_reason', ''),
                'verification_performed': result.get('_verification', {}).get('performed', False),
                'corrected': result.get('_verification', {}).get('corrected', False),
            })
            
            # Progress
            if len(agentic_results) % 50 == 0:
                elapsed = time.time() - start_time
                print(f"Progress: {len(agentic_results)}/{len(trials_df)} | "
                      f"Cost: ${total_cost_agentic:.2f} | "
                      f"Time: {elapsed/60:.1f} min")
                
                # Checkpoint
                pd.DataFrame(agentic_results).to_csv(checkpoint_file, index=False)
        
        except Exception as e:
            print(f"ERROR on {nct_id}: {str(e)}")
            continue
    
    # Save agentic results
    agentic_df = pd.DataFrame(agentic_results)
    agentic_df.to_csv('../output/agentic_all_trials.csv', index=False)
    
    print(f"\n✓ Step 1 complete: {len(agentic_df)} trials categorized")
    print(f"  Total cost: ${total_cost_agentic:.2f}")
    print(f"  Total time: {(time.time() - start_time)/60:.1f} min")
    
    # =========================================================================
    # STEP 2: Filter Tier 1/1.5/2 results
    # =========================================================================
    print("\n" + "="*80)
    print("STEP 2: FILTER HIGH-PRIORITY TRIALS (TIER 1/1.5/2)")
    print("="*80)
    
    high_priority = agentic_df[agentic_df['agentic_tier'].isin([1, 1.5, 2])]
    print(f"\nFiltered {len(high_priority)} high-priority trials:")
    print(high_priority['agentic_tier'].value_counts().sort_index())
    
    # =========================================================================
    # STEP 3: Re-categorize with GPT-5.2
    # =========================================================================
    print("\n" + "="*80)
    print("STEP 3: GPT-5.2 VERIFICATION (TIER 1/1.5/2 ONLY)")
    print("="*80)
    
    gpt52_results = []
    total_cost_gpt52 = 0
    start_time = time.time()
    
    # Check for checkpoint
    checkpoint_file_52 = '../output/gpt52_checkpoint.csv'
    if os.path.exists(checkpoint_file_52):
        existing = pd.read_csv(checkpoint_file_52)
        gpt52_results = existing.to_dict('records')
        print(f"\n✓ Resuming from checkpoint: {len(gpt52_results)} trials completed")
    
    for idx, row in high_priority.iterrows():
        # Skip if already processed
        if any(r['nct_id'] == row['nct_id'] for r in gpt52_results):
            continue
        
        nct_id = row['nct_id']
        
        try:
            # Fetch data
            trial_data = fetch_trial_data(nct_id)
            
            # Categorize with GPT-5.2
            result = categorize_with_gpt52(nct_id, trial_data)
            
            # Calculate cost (approximate)
            meta = result.get('_meta', {})
            input_tokens = meta.get('input_tokens', 0)
            output_tokens = meta.get('output_tokens', 0)
            cost_52 = (input_tokens / 1_000_000) * 1.75 + (output_tokens / 1_000_000) * 14.00
            total_cost_gpt52 += cost_52
            
            # Extract key fields
            gpt52_results.append({
                'nct_id': nct_id,
                'trial_name': trial_data['title'],
                'gpt52_tier': result['classification']['tier'],
                'gpt52_mutation': result['analysis'].get('explicit_mutation_requirement', ''),
                'gpt52_cancer_scope': result['classification'].get('cancer_scope', ''),
                'gpt52_tier_reason': result['classification'].get('tier_reason', ''),
                'agentic_tier': row['agentic_tier'],  # For comparison
            })
            
            # Progress
            if len(gpt52_results) % 10 == 0:
                elapsed = time.time() - start_time
                print(f"Progress: {len(gpt52_results)}/{len(high_priority)} | "
                      f"Cost: ${total_cost_gpt52:.2f} | "
                      f"Time: {elapsed/60:.1f} min")
                
                # Checkpoint
                pd.DataFrame(gpt52_results).to_csv(checkpoint_file_52, index=False)
        
        except Exception as e:
            print(f"ERROR on {nct_id}: {str(e)}")
            continue
    
    # Save GPT-5.2 results
    gpt52_df = pd.DataFrame(gpt52_results)
    gpt52_df.to_csv('../output/gpt52_high_priority.csv', index=False)
    
    print(f"\n✓ Step 3 complete: {len(gpt52_df)} trials re-categorized")
    print(f"  Total cost: ${total_cost_gpt52:.2f}")
    print(f"  Total time: {(time.time() - start_time)/60:.1f} min")
    
    # =========================================================================
    # STEP 4: Merge results (including existing 330)
    # =========================================================================
    print("\n" + "="*80)
    print("STEP 4: MERGE RESULTS (INCLUDING EXISTING 330)")
    print("="*80)
    
    # Load existing 330 GPT-5.2 results
    existing_330 = pd.read_csv('../output/priority_trials_categorized.csv')
    
    # Reformat existing 330 to match our schema
    existing_330_formatted = pd.DataFrame({
        'nct_id': existing_330['nct_id'],
        'trial_name': existing_330['trial_name'],
        'final_tier': existing_330['tier'],
        'final_mutation': existing_330['mutation_type'],
        'final_cancer_scope': existing_330['cancer_scope'],
        'final_tier_reason': existing_330.get('tier_reason', ''),
        'verified_by_gpt52': True,
        'source': 'existing_330'
    })
    
    # Start with agentic results for NEW trials
    final_df = agentic_df.copy()
    
    # Replace with GPT-5.2 results for high-priority
    for idx, row in gpt52_df.iterrows():
        mask = final_df['nct_id'] == row['nct_id']
        final_df.loc[mask, 'final_tier'] = row['gpt52_tier']
        final_df.loc[mask, 'final_mutation'] = row['gpt52_mutation']
        final_df.loc[mask, 'final_cancer_scope'] = row['gpt52_cancer_scope']
        final_df.loc[mask, 'final_tier_reason'] = row['gpt52_tier_reason']
        final_df.loc[mask, 'verified_by_gpt52'] = True
    
    # For non-verified, use agentic results
    final_df['final_tier'] = final_df.get('final_tier', final_df['agentic_tier'])
    final_df['final_mutation'] = final_df.get('final_mutation', final_df['agentic_mutation'])
    final_df['final_cancer_scope'] = final_df.get('final_cancer_scope', final_df['agentic_cancer_scope'])
    final_df['final_tier_reason'] = final_df.get('final_tier_reason', final_df['agentic_tier_reason'])
    final_df['verified_by_gpt52'] = final_df.get('verified_by_gpt52', False)
    final_df['source'] = 'new_agentic'
    
    # Append existing 330
    final_df = pd.concat([final_df, existing_330_formatted], ignore_index=True)
    
    # Save final results
    final_df.to_csv('../output/hybrid_categorization_results.csv', index=False)
    
    print(f"\n✓ Final results saved: {len(final_df)} trials")
    print(f"\nFinal tier distribution:")
    print(final_df['final_tier'].value_counts().sort_index())
    
    print(f"\nVerification breakdown:")
    print(f"  GPT-5.2 verified: {final_df['verified_by_gpt52'].sum()}")
    print(f"  Agentic only: {(~final_df['verified_by_gpt52']).sum()}")
    
    # =========================================================================
    # COST SUMMARY
    # =========================================================================
    print("\n" + "="*80)
    print("COST SUMMARY")
    print("="*80)
    
    # Existing 330 cost: already spent, but count for comparison
    existing_330_cost = len(existing_330) * 0.031
    
    total_cost = total_cost_agentic + total_cost_gpt52
    total_cost_with_existing = total_cost + existing_330_cost
    gpt52_only_cost = len(final_df) * 0.031  # If we had to do ALL with GPT-5.2
    
    print(f"\nHybrid approach (NEW trials only):")
    print(f"  Agentic (new trials):   ${total_cost_agentic:.2f}")
    print(f"  GPT-5.2 (verify T1/T2): ${total_cost_gpt52:.2f}")
    print(f"  Subtotal (new):         ${total_cost:.2f}")
    
    print(f"\nIncluding existing 330 trials:")
    print(f"  GPT-5.2 (330 existing): ${existing_330_cost:.2f} (already spent)")
    print(f"  Total cumulative:       ${total_cost_with_existing:.2f}")
    
    print(f"\nIf we had used GPT-5.2 for ALL {len(final_df)} trials: ${gpt52_only_cost:.2f}")
    print(f"Actual savings: ${gpt52_only_cost - total_cost_with_existing:.2f} ({(1 - total_cost_with_existing/gpt52_only_cost)*100:.1f}%)")
    
    print("\n" + "="*80)
    print("PIPELINE COMPLETE!")
    print("="*80)


if __name__ == '__main__':
    main()

