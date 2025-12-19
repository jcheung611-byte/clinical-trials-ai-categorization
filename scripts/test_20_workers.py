"""
Test 20 workers on 100 trials (5 trials each)
Goal: Verify 20 workers don't hit rate limits with 500 RPM limit
"""

import os
import sys
import json
import time
import pandas as pd
import subprocess

sys.path.insert(0, '..')

def main():
    print("="*80)
    print("TEST: 20 Workers × 5 trials each = 100 trials")
    print("="*80)
    
    # Load dataset
    trials_df = pd.read_csv('../output/exhaustive_search_results_v2.csv')
    trials_df.rename(columns={'NCT Code': 'nct_id'}, inplace=True)
    
    # Load existing
    existing_330 = pd.read_csv('../output/priority_trials_categorized.csv')
    existing_ncts = set(existing_330['nct_id'].values)
    
    # Load checkpoint
    checkpoint_file = '../output/agentic_checkpoint.csv'
    if os.path.exists(checkpoint_file):
        checkpoint_df = pd.read_csv(checkpoint_file)
        existing_ncts.update(checkpoint_df['nct_id'].values)
    
    # Get unprocessed
    remaining_df = trials_df[~trials_df['nct_id'].isin(existing_ncts)]
    
    # Take 100 NEW trials (skip first 200 used in previous tests)
    test_trials = remaining_df.iloc[200:300]['nct_id'].tolist()
    
    print(f"\nTest set: {len(test_trials)} trials")
    print(f"Workers: 20")
    print(f"Trials per worker: {len(test_trials) // 20}")
    print(f"Expected RPM: ~320 (well under 500 RPM limit)")
    
    # Split into 20 batches
    batch_size = len(test_trials) // 20
    batches = [
        test_trials[i*batch_size:(i+1)*batch_size]
        for i in range(20)
    ]
    
    # Create output directory
    output_dir = '../output/parallel_test_20workers'
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\nStarting 20 parallel workers...")
    
    # Launch workers
    processes = []
    for worker_id, batch in enumerate(batches):
        batch_file = f'{output_dir}/batch_{worker_id}.json'
        with open(batch_file, 'w') as f:
            json.dump(batch, f)
        
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
        if worker_id % 5 == 4:
            print(f"✓ Workers 0-{worker_id} started")
    
    print(f"\nAll 20 workers launched! Waiting for completion...")
    
    start_time = time.time()
    completed = 0
    for i, proc in enumerate(processes):
        proc.wait()
        completed += 1
        if completed % 5 == 0:
            elapsed = time.time() - start_time
            print(f"✓ {completed}/20 workers completed ({elapsed/60:.1f} min elapsed)")
    
    total_time = time.time() - start_time
    
    # Merge results
    all_results = []
    errors = 0
    for worker_id in range(20):
        result_file = f'{output_dir}/worker_{worker_id}_results.csv'
        log_file = f'{output_dir}/worker_{worker_id}_log.txt'
        
        # Check for rate limit errors in log
        if os.path.exists(log_file):
            with open(log_file) as f:
                log_content = f.read()
                if '429' in log_content or 'rate limit' in log_content.lower():
                    errors += 1
        
        if os.path.exists(result_file):
            df = pd.read_csv(result_file)
            all_results.append(df)
    
    if all_results:
        merged_df = pd.concat(all_results, ignore_index=True)
        merged_df.to_csv(f'{output_dir}/merged_results.csv', index=False)
        
        print(f"\n{'='*80}")
        print("20-WORKER TEST COMPLETE!")
        print("="*80)
        print(f"\nResults:")
        print(f"  Trials processed: {len(merged_df)}/100")
        print(f"  Total time: {total_time/60:.1f} minutes")
        print(f"  Avg time/trial: {total_time/len(merged_df):.1f} seconds")
        print(f"  Workers with rate limit errors: {errors}/20")
        
        if errors == 0:
            print(f"\n✅ Test successful! Safe to run 20 workers on full dataset.")
            print(f"   Expected time for 2,734 trials: ~{2734 * (total_time/len(merged_df)) / 60 / 20:.1f} minutes")
        else:
            print(f"\n⚠️  Rate limits detected! Stick with 10 workers instead.")
    else:
        print(f"\n❌ No results found - check logs for errors")


if __name__ == '__main__':
    main()

