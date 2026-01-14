from ticker import Ticker
from pair import Pair
import pandas as pd
import numpy as np
import sqlite3
from functools import partial

nse_fno_lots = pd.read_csv('nse_fno_lots.csv')

y = int(np.where(nse_fno_lots['Symbol'] == 'YESBANK')[0])
x = int(np.where(nse_fno_lots['Symbol'] == 'INDUSINDBK')[0])
ticker1 = Ticker(nse_fno_lots.iloc[y])
ticker2 = Ticker(nse_fno_lots.iloc[x])

conn   = sqlite3.connect('pair_trading.db')
conn.execute("PRAGMA journal_mode = WAL;")

cursor = conn.cursor()
cursor.execute("DROP TABLE IF EXISTS test_stats")
cursor.execute("""
CREATE TABLE test_stats (
    sl      REAL,
    min_z   REAL,
    max_z   REAL,
    avg_p   REAL,
    pnl     REAL
)
""")
conn.commit()

windows   = [250, 275, 300, 325, 350, 375, 400]
params    = [2.5 ,3 ,3.5]
p_ths   = [0.05, 0.10]
corr_ths = [0.8, 0.9]
for sl in params:
    pair = Pair(ticker1, ticker2, 300, 2, 1, sl, 0.1, 0.9)
    df = pair.fetch_table()
    
    min_z = df['Z_value'].min()
    max_z = df['Z_value'].max()
    avg_p = df['ADF_p_value'].mean()
    pnl = df['Cumulative_PnL'].iloc[-1]

    # insert into SQLite
    cursor.execute("""
        INSERT INTO test_stats (sl, min_z, max_z, avg_p, pnl)
        VALUES (?, ?, ?, ?, ?)
    """, (sl, min_z, max_z, avg_p, pnl))
    print(sl, min_z, max_z, avg_p, pnl)
    # 4. finalize
    conn.commit()
conn.close()

