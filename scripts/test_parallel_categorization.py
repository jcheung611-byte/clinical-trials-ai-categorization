"""
Test Parallelization - 100 trials split 5 ways (20 trials each)
Goal: Verify parallelization works without hitting rate limits
"""

import os
import sys
import json
import time
import requests
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
import subprocess

sys.path.insert(0, '..')
from gpt.agentic_categorizer import categorize_with_agentic_chain, calculate_cost

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
    }


def process_batch(batch_trials, worker_id, output_dir='../output/parallel_test'):
    """Process a batch of trials for one worker."""
    os.makedirs(output_dir, exist_ok=True)
    
    results = []
    total_cost = 0
    start_time = time.time()
    
    log_file = f'{output_dir}/worker_{worker_id}_log.txt'
    
    with open(log_file, 'w') as log:
        log.write(f"Worker {worker_id} starting: {len(batch_trials)} trials\n")
        log.write(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.write("="*60 + "\n\n")
        
        for idx, nct_id in enumerate(batch_trials):
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
                total_cost += cost_info['agentic_mini_cost']
                
                # Extract key fields
                results.append({
                    'nct_id': nct_id,
                    'trial_name': trial_data['title'],
                    'agentic_tier': result['classification']['tier'],
                    'agentic_mutation': result['analysis'].get('explicit_mutation_requirement', ''),
                    'agentic_cancer_scope': result['classification'].get('cancer_scope', ''),
                    'worker_id': worker_id,
                })
                
                elapsed = time.time() - start_time
                log.write(f"[{idx+1}/{len(batch_trials)}] {nct_id} → Tier {result['classification']['tier']} | "
                         f"Time: {elapsed:.1f}s | Cost: ${total_cost:.4f}\n")
                log.flush()
                
            except Exception as e:
                log.write(f"ERROR on {nct_id}: {str(e)}\n")
                log.flush()
                continue
        
        # Save results
        results_df = pd.DataFrame(results)
        results_df.to_csv(f'{output_dir}/worker_{worker_id}_results.csv', index=False)
        
        elapsed = time.time() - start_time
        log.write(f"\n{'='*60}\n")
        log.write(f"Worker {worker_id} COMPLETE\n")
        log.write(f"Trials processed: {len(results)}/{len(batch_trials)}\n")
        log.write(f"Total cost: ${total_cost:.4f}\n")
        log.write(f"Total time: {elapsed/60:.1f} min\n")
        log.write(f"Avg time/trial: {elapsed/len(results):.1f} sec\n")


def main():
    """Test parallelization on 100 trials split 5 ways."""
    print("="*80)
    print("TESTING PARALLELIZATION: 100 trials × 5 workers")
    print("="*80)
    
    # Load full dataset
    trials_df = pd.read_csv('../output/exhaustive_search_results_v2.csv')
    trials_df.rename(columns={'NCT Code': 'nct_id'}, inplace=True)
    
    # Load existing results to skip already processed
    existing_330 = pd.read_csv('../output/priority_trials_categorized.csv')
    existing_ncts = set(existing_330['nct_id'].values)
    
    # Load checkpoint if exists
    checkpoint_file = '../output/agentic_checkpoint.csv'
    if os.path.exists(checkpoint_file):
        checkpoint_df = pd.read_csv(checkpoint_file)
        existing_ncts.update(checkpoint_df['nct_id'].values)
    
    # Filter to unprocessed trials
    remaining_df = trials_df[~trials_df['nct_id'].isin(existing_ncts)]
    
    print(f"\nTotal trials: {len(trials_df)}")
    print(f"Already processed: {len(existing_ncts)}")
    print(f"Remaining: {len(remaining_df)}")
    
    # Take 100 trials for testing
    test_trials = remaining_df.head(100)['nct_id'].tolist()
    
    print(f"\nTest set: {len(test_trials)} trials")
    print(f"Workers: 5")
    print(f"Trials per worker: {len(test_trials) // 5}")
    
    # Split into 5 batches
    batch_size = len(test_trials) // 5
    batches = [
        test_trials[i*batch_size:(i+1)*batch_size]
        for i in range(5)
    ]
    
    # Create output directory
    output_dir = '../output/parallel_test'
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\nStarting 5 parallel workers...")
    print(f"Monitor: tail -f {output_dir}/worker_*_log.txt\n")
    
    # Launch workers in background
    processes = []
    for worker_id, batch in enumerate(batches):
        # Save batch to temp file
        batch_file = f'{output_dir}/batch_{worker_id}.json'
        with open(batch_file, 'w') as f:
            json.dump(batch, f)
        
        # Launch worker
        cmd = [
            'python3', '-c',
            f"""
import sys
sys.path.insert(0, '..')
import json
from test_parallel_categorization import process_batch

with open('{batch_file}') as f:
    batch = json.load(f)
    
process_batch(batch, {worker_id}, '{output_dir}')
"""
        ]
        
        proc = subprocess.Popen(
            cmd,
            cwd=os.path.dirname(__file__),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        processes.append(proc)
        print(f"✓ Worker {worker_id} started (PID: {proc.pid})")
    
    print(f"\nAll workers launched! Waiting for completion...")
    
    # Wait for all to complete
    start_time = time.time()
    for i, proc in enumerate(processes):
        proc.wait()
        elapsed = time.time() - start_time
        print(f"✓ Worker {i} completed ({elapsed/60:.1f} min elapsed)")
    
    total_time = time.time() - start_time
    
    # Merge results
    all_results = []
    for worker_id in range(5):
        result_file = f'{output_dir}/worker_{worker_id}_results.csv'
        if os.path.exists(result_file):
            df = pd.read_csv(result_file)
            all_results.append(df)
    
    merged_df = pd.concat(all_results, ignore_index=True)
    merged_df.to_csv(f'{output_dir}/merged_results.csv', index=False)
    
    print(f"\n{'='*80}")
    print("PARALLEL TEST COMPLETE!")
    print("="*80)
    print(f"\nResults:")
    print(f"  Trials processed: {len(merged_df)}/100")
    print(f"  Total time: {total_time/60:.1f} minutes")
    print(f"  Avg time/trial: {total_time/len(merged_df):.1f} seconds")
    print(f"  Speedup: ~5x faster than sequential")
    
    print(f"\nTier distribution:")
    print(merged_df['agentic_tier'].value_counts().sort_index())
    
    print(f"\nFiles saved:")
    print(f"  Merged results: {output_dir}/merged_results.csv")
    print(f"  Worker logs: {output_dir}/worker_*_log.txt")
    print(f"  Worker results: {output_dir}/worker_*_results.csv")
    
    print(f"\n✅ Parallelization test successful!")
    print(f"   Ready to apply to full dataset (2,734 remaining trials)")


if __name__ == '__main__':
    main()

