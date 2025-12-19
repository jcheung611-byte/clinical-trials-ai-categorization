"""
Spot-check Tier 3s and 4s with GPT-5.2 and GPT-5-mini
to identify any that should be re-categorized to Tier 1/1.5/2
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

load_dotenv('../.env')
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))


def fetch_trial_data(nct_id):
    """Fetch trial data from ClinicalTrials.gov API."""
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


def call_gpt4_model(model_name, prompt):
    """Call GPT-4 models via Chat Completions API."""
    start = time.time()
    
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {'role': 'system', 'content': 'Expert clinical trial analyst. JSON only.'},
            {'role': 'user', 'content': prompt}
        ],
        response_format={'type': 'json_object'},
        temperature=0.1,
        max_tokens=700,
    )
    
    latency = time.time() - start
    result = json.loads(response.choices[0].message.content)
    
    return {
        'result': result,
        'latency': latency,
    }


def call_gpt5_model(model_name, prompt):
    """Call GPT-5 models via Responses API."""
    start = time.time()
    
    # Add JSON instruction to prompt
    json_prompt = prompt + "\n\nRespond with ONLY valid JSON in the exact format specified above."
    
    response = client.responses.create(
        model=model_name,
        input=json_prompt,
    )
    
    latency = time.time() - start
    
    # Extract text from response
    text = None
    for item in response.output:
        if hasattr(item, 'type') and item.type == 'message':
            if hasattr(item, 'content') and len(item.content) > 0:
                text = item.content[0].text
                break
    
    if not text:
        raise ValueError(f"Could not extract text from response")
    
    # Parse JSON
    result = json.loads(text)
    
    return {
        'result': result,
        'latency': latency,
    }


def categorize_trial(nct_id, original_tier, trial_data):
    """Categorize a single trial with both gpt-5.2 and gpt-5-mini."""
    print(f"\n{nct_id} (Original: Tier {original_tier})")
    
    # Generate prompt
    prompt = get_trial_categorization_prompt(
        nct_id,
        trial_data['title'],
        trial_data['official_title'],
        trial_data['conditions'],
        trial_data['interventions'],
        trial_data['brief_summary'],
        trial_data['eligibility']
    )
    
    results = {}
    
    # Test both models
    for model_name, is_gpt5 in [('gpt-5.2', True), ('gpt-5-mini', True)]:
        try:
            if is_gpt5:
                response_data = call_gpt5_model(model_name, prompt)
            else:
                response_data = call_gpt4_model(model_name, prompt)
            
            tier = response_data['result'].get('classification', {}).get('tier', '?')
            mutation = response_data['result'].get('analysis', {}).get('explicit_mutation_requirement', '')
            cancer = response_data['result'].get('classification', {}).get('cancer_scope', '')
            reason = response_data['result'].get('classification', {}).get('tier_reason', '')
            
            results[model_name] = {
                'tier': str(tier),
                'mutation': mutation,
                'cancer': cancer,
                'reason': reason,
                'latency': response_data['latency'],
            }
            
            # Show immediately
            change_flag = '⬆️ MOVED UP!' if str(tier) in ['1', '1.5', '2'] else ''
            print(f"  {model_name}: Tier {tier} {change_flag} ({response_data['latency']:.1f}s)")
            
        except Exception as e:
            print(f"  {model_name}: ERROR - {str(e)[:60]}")
            results[model_name] = {'error': str(e)}
    
    return results


def main():
    """Run spot-check on Tier 3s and 4s."""
    print("="*80)
    print("TIER 3/4 SPOT-CHECK: GPT-5.2 vs GPT-5-mini")
    print("="*80)
    
    # Load samples
    samples = pd.read_csv('tier_3_4_samples.csv')
    
    print(f"\nTesting {len(samples)} trials:")
    print(f"  {len(samples[samples['tier_num'] == 3])} Tier 3s (Colon, no RAS)")
    print(f"  {len(samples[samples['tier_num'] == 4])} Tier 4s (Non-colon/non-RAS)")
    
    results_list = []
    moved_up_count = {'gpt-5.2': 0, 'gpt-5-mini': 0}
    
    for idx, row in samples.iterrows():
        nct_id = row['NCT Code']
        original_tier = row['tier_num']
        
        try:
            # Fetch trial data
            trial_data = fetch_trial_data(nct_id)
            
            # Categorize with both models
            model_results = categorize_trial(nct_id, original_tier, trial_data)
            
            # Track if moved up
            for model_name in ['gpt-5.2', 'gpt-5-mini']:
                if model_name in model_results and 'tier' in model_results[model_name]:
                    new_tier = model_results[model_name]['tier']
                    if new_tier in ['1', '1.5', '2']:
                        moved_up_count[model_name] += 1
            
            # Save result
            result_row = {
                'nct_id': nct_id,
                'original_tier': original_tier,
                'original_priority': row['Priority'],
                'title': trial_data['title'][:80],
            }
            
            for model_name in ['gpt-5.2', 'gpt-5-mini']:
                if model_name in model_results:
                    prefix = model_name.replace('-', '_').replace('.', '_')
                    for key, val in model_results[model_name].items():
                        result_row[f'{prefix}_{key}'] = val
            
            results_list.append(result_row)
            
            # Save periodically
            if len(results_list) % 10 == 0:
                pd.DataFrame(results_list).to_csv('tier_3_4_recat_results_partial.csv', index=False)
                print(f"\n  Progress: {len(results_list)}/{len(samples)} trials processed")
        
        except Exception as e:
            print(f"  ERROR processing {nct_id}: {str(e)[:60]}")
            continue
    
    # Save final results
    results_df = pd.DataFrame(results_list)
    results_df.to_csv('tier_3_4_recat_results.csv', index=False)
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    print(f"\nTrials that MOVED UP to Tier 1/1.5/2:")
    print(f"  gpt-5.2:   {moved_up_count['gpt-5.2']}/{len(samples)} ({moved_up_count['gpt-5.2']/len(samples)*100:.1f}%)")
    print(f"  gpt-5-mini: {moved_up_count['gpt-5-mini']}/{len(samples)} ({moved_up_count['gpt-5-mini']/len(samples)*100:.1f}%)")
    
    # Show trials that moved up
    print("\n" + "="*80)
    print("TRIALS MOVED UP BY GPT-5.2:")
    print("="*80)
    
    moved_up_52 = results_df[results_df['gpt_5_2_tier'].isin(['1', '1.5', '2'])]
    if len(moved_up_52) > 0:
        for idx, row in moved_up_52.iterrows():
            print(f"\n{row['nct_id']} (was Tier {row['original_tier']} → now Tier {row['gpt_5_2_tier']})")
            print(f"  Title: {row['title']}")
            print(f"  Mutation: {row.get('gpt_5_2_mutation', 'N/A')}")
            print(f"  Cancer: {row.get('gpt_5_2_cancer', 'N/A')}")
            print(f"  Reason: {row.get('gpt_5_2_reason', 'N/A')[:80]}")
    else:
        print("None found.")
    
    print("\n" + "="*80)
    print("TRIALS MOVED UP BY GPT-5-MINI:")
    print("="*80)
    
    moved_up_mini = results_df[results_df['gpt_5_mini_tier'].isin(['1', '1.5', '2'])]
    if len(moved_up_mini) > 0:
        for idx, row in moved_up_mini.iterrows():
            print(f"\n{row['nct_id']} (was Tier {row['original_tier']} → now Tier {row['gpt_5_mini_tier']})")
            print(f"  Title: {row['title']}")
            print(f"  Mutation: {row.get('gpt_5_mini_mutation', 'N/A')}")
            print(f"  Cancer: {row.get('gpt_5_mini_cancer', 'N/A')}")
            print(f"  Reason: {row.get('gpt_5_mini_reason', 'N/A')[:80]}")
    else:
        print("None found.")
    
    print("\n" + "="*80)
    print(f"Results saved to: tier_3_4_recat_results.csv")
    print("="*80)


if __name__ == '__main__':
    main()

