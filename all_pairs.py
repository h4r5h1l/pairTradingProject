import sqlite3
import pandas as pd
from ticker import Ticker

def get_open_positions():
    """
    Connects to the pair_trading.db, retrieves all pair tables,
    and checks the last row for any open positions.
    Prints the pair and the position if a position is open.
    """
    conn = sqlite3.connect('pair_trading.db')
    cursor = conn.cursor()

    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    print("Checking for open positions...")

    for table_name in tables:
        table_name = table_name[0]
        # Pair tables have an underscore in their name and are not pair_plots
        if '_' in table_name and table_name != 'pair_plots':
            try:
                # Read the last row of the table
                df = pd.read_sql(f'SELECT * FROM "{table_name}" ORDER BY Date DESC LIMIT 1', conn)
                if not df.empty:
                    position = df['Position'].iloc[-1]
                    if position != 0:
                        print(f"Open position in {table_name}: {'Long' if position == 1 else 'Short'}")
            except Exception as e:
                # This will catch cases where a table might not have the 'Position' column
                # or other reading errors, making the script more robust.
                pass
    conn.close()

def create_trades_table():
    conn = sqlite3.connect('pair_trading.db')
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS all_trades")
    conn.commit()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS all_trades (
            start TEXT,
            end TEXT,
            y_name TEXT,
            x_name TEXT,
            slope REAL,
            y_lotsize INTEGER,
            x_lotsize INTEGER,           
            n_x_lots REAL,
            err_ratio REAL,
            z_open REAL,
            z_close REAL,
            p_open REAL,
            p_close REAL,
            corr_open REAL,
            corr_close REAL,
            position INTEGER,
            pnl REAL
        )
    ''')
    conn.commit()

    # Load lot sizes
    lot_sizes = pd.read_csv('nse_fno_lots.csv', index_col='Symbol')['LotSize']

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    all_trades = []

    for table_name in tables:
        table_name = table_name[0]
        if '_' in table_name and table_name != 'pair_plots':
            y_name, x_name = table_name.split('_')
            try:
                df = pd.read_sql(f'SELECT * FROM "{table_name}"', conn, index_col='Date', parse_dates=['Date'])
            except KeyError:
                print(f"Skipping `{table_name}` is not a pair, Exception: no Date column.")
                continue

            df['Trade_Block'] = (df['Position'] != df['Position'].shift()).cumsum() 
            trades = df[df['Position'] != 0].groupby('Trade_Block')

            for trade_id, trade_df in trades:
                start_ts = trade_df.index.min()
                # get_indexer always returns an array of positions (or -1 if missing)
                try:
                    start_pos = df.index.to_list().index(start_ts)
                except ValueError:
                # somehow the timestamp isn't in df.index — skip
                    continue
                if start_pos == 0:
                    # trade starts on the very first row—nothing to prepend
                    continue

                # grab the one-row signal‐trigger row by .iloc
                signal_row = df.iloc[[start_pos - 1]]

                # now concat that to your trade_df
                trade_df = pd.concat([signal_row, trade_df]).sort_index()

                start_date = trade_df.index.min()
                end_date   = trade_df.index.max()
                trade_pnl = trade_df['PnL'].sum()

                slope = trade_df['Slope'].iloc[0]
                y_lot = int(lot_sizes.get(y_name, 0))
                x_lot = int(lot_sizes.get(x_name, 0))
                n_x_lots = (slope*y_lot)/x_lot
                
                trade_data = {
                    'start': start_date.strftime('%Y-%m-%d'),
                    'end': end_date.strftime('%Y-%m-%d'),
                    'y_name': y_name,
                    'x_name': x_name,
                    'slope': slope,
                    'y_lotsize': y_lot,
                    'x_lotsize': x_lot,              
                    'n_x_lots': n_x_lots,
                    'err_ratio': trade_df['Err_Ratio'].iloc[0],
                    'z_open': trade_df['Z_value'].iloc[0],
                    'z_close': trade_df['Z_value'].iloc[-1],
                    'p_open': trade_df['ADF_p_value'].iloc[0],
                    'p_close': trade_df['ADF_p_value'].iloc[-1],
                    'corr_open': trade_df['Correlation'].iloc[0],
                    'corr_close': trade_df['Correlation'].iloc[-1],
                    'position': trade_df['Position'].iloc[1],
                    'pnl': trade_pnl
                }
                all_trades.append(trade_data)

    if all_trades:
        # Sort trades by start date
        all_trades_df = pd.DataFrame(all_trades)
        all_trades_df.sort_values(by='start', inplace=True)

        # Insert sorted data into the table
        all_trades_df.to_sql('all_trades', conn, if_exists='append', index=False)

    conn.close()
