import multiprocessing
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from time import time
from datetime import timedelta
from all_pairs import get_open_positions, create_trades_table
from ticker import Ticker
from itertools import permutations
from pair import Pair
def process_pair(job): 
    y, x, sector = job
    pair = Pair(y, x, sector, 300, 2, 1, 3, 0.1, 0.9)
    return pair.table_name
if __name__ == "__main__":
    start = time()
    nse_fno_lots = pd.read_csv('nse_fno_lots.csv')
    for _, row in nse_fno_lots.iterrows():
        if row['Sector'] not in ['Index', 'ETF']:
            t = Ticker(row)
    sector_groups = nse_fno_lots.groupby("Sector")
    sectors = {sector: group[['Symbol', 'LotSize', 'Sector']] for sector, group in sector_groups 
               if len(group) > 1 and sector not in ['Index', 'ETF']}
    jobs = [ (y, x, sector) for sector, df in sectors.items() 
            for y, x in permutations(df['Symbol'], 2) ]
    print(f"Dispatching {len(jobs)} jobs…")
    results = []
    n_cores = multiprocessing.cpu_count()
    with ProcessPoolExecutor(max_workers=n_cores) as exe:
        future_to_job = {exe.submit(process_pair, job): job for job in jobs}
        for fut in as_completed(future_to_job):
            y_row, x_row, sector = future_to_job[fut]
            try:
                name = fut.result()
                print(f"✅ {name} done")
                results.append(name)
            except Exception as e:
                print(f"❌ {y_row}_{x_row} failed:", e)
    end = time()
    print(f"Time Taken: {str(timedelta(seconds = (end - start)))}")
    create_trades_table()
    print("Successfully created and populated the 'all_trades' table.")
    get_open_positions()