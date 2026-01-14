from ticker import Ticker
from pair import Pair
import pandas as pd
import numpy as np
import sqlite3

nse_fno_lots = pd.read_csv('nse_fno_lots.csv')

y = 'HCLTECH'
x = 'TECHM'
ticker1 = Ticker(nse_fno_lots[nse_fno_lots['Symbol'] == y].iloc[0])
ticker2 = Ticker(nse_fno_lots[nse_fno_lots['Symbol'] == x].iloc[0])
sector = ticker1.sector  # Assuming both tickers belong to the same sector
pair = Pair(y, x,  sector, window=300, entry=2, exit=1, sl=3, p_th=0.1, corr_th=0.9)
pair.show_plot()


