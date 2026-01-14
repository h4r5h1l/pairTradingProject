import sqlite3
import numpy as np
import pandas as pd
import statsmodels.api as sm
import matplotlib.pyplot as plt
import io
from ticker import Ticker

class Pair:
    def __init__(self, y: str, x: str, sector: str, window: int, entry: float, exit: float, sl: float, p_th: float, corr_th: float):
        self.conn = sqlite3.connect('pair_trading.db')
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.sector = sector
        self.y = y
        self.x = x
        self.table_name = f'{y}_{x}'

        cursor = self.conn.cursor()
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{self.table_name}'")
        pair_table_exists = cursor.fetchone() is not None

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='all_trades'")
        all_trades_exists = cursor.fetchone() is not None

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pair_plots'")
        pair_plots_exists = cursor.fetchone() is not None

        if pair_table_exists and all_trades_exists and pair_plots_exists:
            self.update(window, entry, exit, sl, p_th, corr_th)
        else:
            y_df = pd.read_sql(f'SELECT * FROM "{y}"', self.conn, index_col='Date')
            x_df = pd.read_sql(f'SELECT * FROM "{x}"', self.conn, index_col='Date')
            self.df = self._merge_ticker_dfs(y_df, x_df)
            self.df = self._calc_rolling_metrics(self.df, window)
            self.df = self._calc_signals_pnl(self.df, entry, exit, sl, p_th, corr_th, window)
            self._write_to_sql()

            self.conn.executescript(f'''
                CREATE TABLE IF NOT EXISTS "pair_plots" (
                    name TEXT,
                    plot BLOB,
                    Cumulative_PnL REAL,
                    Max_Drawdown REAL,
                    Sector TEXT,
                    n_Longs INTEGER,
                    n_Shorts INTEGER,
                    n_Trades INTEGER,
                    n_Profits INTEGER,
                    n_Losses INTEGER
                );
                DELETE FROM "pair_plots" WHERE name = "{self.table_name}";
            ''')
            self.conn.commit()
            self._plot_positions(self.df, entry, exit, sl, p_th, corr_th, window)
            self.conn.commit()

        self.conn.close()

    def _merge_ticker_dfs(self, df_y, df_x):
        # rename columns to avoid clashes
        df_y = df_y.rename(columns={
            'Close':       f'{self.y}_Close',
            # 'LogReturns':  f'{self.y_name}_LogReturns'
        })
        df_x = df_x.rename(columns={
            'Close':       f'{self.x}_Close',
            # 'LogReturns':  f'{self.x_name}_LogReturns'
        })
        # inner‐join on the Date index
        merged =    df_y[[f'{self.y}_Close']].join(
                    df_x[[f'{self.x}_Close']],
                     how='inner'
                 )
        return merged

    def _calc_rolling_metrics(self, df, window):
        # prepare empty columns
        for col in ['Slope','Intercept','Err_Ratio','Z_value','Correlation','ADF_p_value']:
            df[col] = np.nan

        ys = df[f'{self.y}_Close'].values
        xs = df[f'{self.x}_Close'].values
        dates = df.index

        for i in range(window-1, len(df)):
            y_win = ys[i-window+1 : i+1]
            x_win = xs[i-window+1 : i+1]
            X_mat = sm.add_constant(x_win)
            model = sm.OLS(y_win, X_mat).fit()
            resid = model.resid
            std_err = np.sqrt(model.mse_resid)
            std_err_int = model.bse[0]

            df.at[dates[i], 'Slope']        = round(model.params[1], 5)
            df.at[dates[i], 'Intercept']    = round(model.params[0], 2)
            df.at[dates[i], 'Err_Ratio']    = round(std_err_int/std_err, 2)
            df.at[dates[i], 'Z_value']      = round(resid[-1] / std_err, 3)
            df.at[dates[i], 'Correlation']  = round(np.corrcoef(x_win, y_win)[0,1], 3)
            df.at[dates[i], 'ADF_p_value']  = round(sm.tsa.stattools.adfuller(resid)[1], 4)

        return df

    def _calc_signals_pnl(self, df, entry, exit, sl, p_th, corr_th, window):
        df['Signal'] = np.nan
        # identify stationarity & z‐diff
        stationary = p_th > df['ADF_p_value'].rolling(3).max()
        z_diff     = df['Z_value'].diff()

        # entry signals
        short_enter = (df['Z_value'] >=  entry) & (df['Z_value'] <  sl) & (z_diff >= 0) & (df['Z_value'] < df['Z_value'].rolling(2).max()) & (df['Correlation'] >= corr_th) & stationary & (df['Slope'] > 0)
        
        long_enter  = (df['Z_value'] <= -(entry)) & (df['Z_value'] > -(sl)) & (z_diff >= 0) & (df['Z_value'] > df['Z_value'].rolling(2).min()) & (df['Correlation']>= corr_th) & stationary & (df['Slope'] > 0) 
                    
        df.loc[ long_enter, 'Signal'] =  1
        df.loc[ short_enter, 'Signal'] = -1

        # Forward-fill signal
        df['Position'] = df['Signal'].ffill().fillna(0)
        in_long = df['Position'] == 1
        in_short = df['Position'] == -1
        
        # exit signals
        long_exit  = in_long  & ((df['Z_value'] >= -(exit)) | (df['Z_value'] < -(sl))) | (~stationary) | (df['Correlation'] < corr_th)
        short_exit = in_short & ((df['Z_value'] <=  (exit)) | (df['Z_value'] >  (sl))) | (~stationary) | (df['Correlation'] < corr_th)
        exit_condition = long_exit | short_exit    
        df.loc[ exit_condition, 'Signal'] = 0
        
        # build position and then shift to establish position.
        df['Position'] = df['Signal'].ffill().fillna(0).shift()
        df['y_returns']       = round(df[f'{self.y}_Close'].pct_change(), 5).fillna(0)
        df['mx_returns']    = round(-((df[f'{self.x}_Close']*df['Slope']).pct_change()), 5).fillna(0)
        df['PnL']       = round(df['Position'].fillna(0) * (df['y_returns'] + df['mx_returns']), 5)
        df['Cumulative_PnL'] = round(df['PnL'].cumsum(), 5)
        df['Drawdown'] = round(df['Cumulative_PnL'].cummax()- df['Cumulative_PnL'], 5)
        
        return df

    def _plot_positions(self, df, entry, exit, sl, p_th, corr_th, window):

        fig, (ax1, ax2) = plt.subplots(2,1, sharex=True, figsize=(14,10))

        # 2) Plot Z_value and thresholds
        df['Z_value'].plot(ax=ax1, color='blue', label='Z_value', linewidth=0.5)
        for lvl, style, col in [(-(entry),'--','green'), (entry,'--','green'),
                                (-(sl),'-.','red'), (sl,'-.','red')]:
            ax1.axhline(lvl, linestyle=style, color=col, linewidth=1)

        # 1) Z_value shading and twin axis setup with aligned zeros
        ax1b = ax1.twinx()
        
        # Plot secondary axis data first to establish ranges
        df['Position'].plot(ax=ax1b, style='green', label='Position', linewidth=0.1)
        df['Correlation'].plot(ax=ax1b, style="#7C3001", label='Correlation', linewidth=0.5)
        df['ADF_p_value'].plot(ax=ax1b, style="#5E006A", label='ADF P-Value', linewidth=0.5)
        
        # Get current limits after plotting
        lo1, hi1 = ax1.get_ylim()
        lo2, hi2 = ax1b.get_ylim()
        
        # Align zero lines by adjusting ax1b limits
        # Calculate where zero should be positioned on ax1
        if lo1 < 0 < hi1:  # ax1 spans zero
            zero_ratio = -lo1 / (hi1 - lo1)  # Position of zero as fraction from bottom
            
            # Adjust ax1b to place zero at the same relative position
            range2 = hi2 - lo2
            new_lo2 = -zero_ratio * range2
            new_hi2 = (1 - zero_ratio) * range2
            ax1b.set_ylim(new_lo2, new_hi2)
            lo2, hi2 = new_lo2, new_hi2

        # Apply shading with current limits
        ax1.fill_between(df.index, -(exit), exit, color='lightgreen', alpha=0.3)
        ax1.fill_between(df.index, lo1, -(sl),  color='red', alpha=0.1)
        ax1.fill_between(df.index, sl, hi1,   color='red', alpha=0.1)
        
        # 3) Correlation and ADF P-Value shading 
        Threshold = (df['Correlation'] < corr_th) |(df['ADF_p_value'] > p_th)
        Long = df['Position'] == 1 
        Short = df['Position'] == -1
        ax1.fill_between(df.index, lo1, hi1, where=Threshold, color="grey", alpha=0.3)
        ax1.fill_between(df.index, lo1, hi1, where=Long, color="Green", alpha=0.5)
        ax1.fill_between(df.index, lo1, hi1, where=Short, color="Red", alpha=0.5)
        
        # 4) Set labels and legends
        ax1.set_ylabel('Z-Value')
        ax1b.set_ylabel('Position / Correlation/ ADF P-Value')
        ax1.legend(loc='upper left')
        ax1b.legend(loc='upper right')
        ax1.grid(True)
        
        # 5) Bottom plot: Cumulative PnL
        df['Cumulative_PnL'].plot(ax=ax2, color='black', label='Cum. PnL')
        ax2.set_ylabel('Cumulative PnL')
        ax2.set_xlabel('Date')
        ax2.legend(loc='upper left')
        ax2.grid(True)
        
        # 6) Super‐title and save/show
        max_dd = df['Drawdown'].max()
        fig.suptitle(f"Backtest for {self.table_name} – Final Max DD: {max_dd:.2f}")
        fig.tight_layout(rect=[0,0.03,1,0.95])

        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        img_bytes = buf.read()
        df_t = df.iloc[window-1:].copy()
        entry = (df_t['Position'].shift() == 0) & (df_t['Position'] != 0)
        longs = (df_t['Position'].shift() == 0) & (df_t['Position'] == 1)
        shorts = (df_t['Position'].shift() == 0) & (df_t['Position'] == -1)

        n_longs = int(longs.sum())
        n_shorts = int(shorts.sum())
        n_trades = int(entry.sum())
        
        df_t['Trade_Block'] = entry.cumsum()
        df_t.loc[df_t['Position'] == 0, 'Trade_Block'] = 0
        trade_pnls = df_t[df_t['Trade_Block'] != 0].groupby('Trade_Block')['PnL'].sum()
        n_profits = int((trade_pnls > 0).sum())
        n_losses = int((trade_pnls < 0).sum())

        # Store the plot in the database
        self.conn.execute(f'''
            INSERT INTO "pair_plots" (name, plot, Cumulative_PnL, Max_Drawdown, Sector, n_Longs, n_Shorts, n_Trades, n_Profits, n_Losses)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (f'{self.table_name}', sqlite3.Binary(img_bytes), df['Cumulative_PnL'].iloc[-1], df['Drawdown'].max(), self.sector, n_longs, n_shorts, n_trades, n_profits, n_losses))

        self.conn.commit()
        plt.close(fig)
        

    def _write_to_sql(self):
        self.df.to_sql(self.table_name,
                       self.conn,
                       if_exists='replace',
                       index=True,
                       index_label='Date')

    def fetch_table(self):
        conn =  sqlite3.connect('pair_trading.db')
        query = f'SELECT * FROM "{self.table_name}"'
        return pd.read_sql(query, conn, index_col='Date')
    
    def show_plot(self):

        pair_name = self.table_name
        blob = sqlite3.connect("pair_trading.db").execute("""
        SELECT plot FROM pair_plots WHERE name = ?""", (pair_name,)).fetchone()[0]

        buf = io.BytesIO(blob)
        plt.figure(figsize=(10, 6))
        plt.imshow(plt.imread(buf), aspect='auto')
        plt.axis('off')
        plt.title(pair_name)
        return plt.show()

    def update(self, window: int, entry: float, exit: float, sl: float, p_th: float, corr_th: float):
        self.conn = sqlite3.connect('pair_trading.db')
        self.conn.execute("PRAGMA journal_mode = WAL;")

        cursor = self.conn.cursor()
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{self.table_name}'")
        if cursor.fetchone() is None:
            print(f"Table {self.table_name} does not exist. Please create it first.")
            self.conn.close()
            return

        last_date_pair_str = pd.read_sql(f'SELECT MAX(Date) FROM "{self.table_name}"', self.conn).iloc[0, 0]
        last_date_y_str = pd.read_sql(f'SELECT MAX(Date) FROM "{self.y}"', self.conn).iloc[0, 0]

        if last_date_pair_str is None or last_date_y_str is None:
            print("Could not determine last date from tables.")
            self.conn.close()
            return

        if pd.to_datetime(last_date_pair_str) < pd.to_datetime(last_date_y_str):
            print(f"Updating pair {self.table_name}...")
            
            # Fetch only new data
            y_df_new = pd.read_sql(f'SELECT * FROM "{self.y}" WHERE Date > "{last_date_pair_str}"', self.conn, index_col='Date')
            x_df_new = pd.read_sql(f'SELECT * FROM "{self.x}" WHERE Date > "{last_date_pair_str}"', self.conn, index_col='Date')

            if y_df_new.empty or x_df_new.empty:
                print("No new data to update.")
                self.conn.close()
                return

            # Merge new ticker data
            df_new = self._merge_ticker_dfs(y_df_new, x_df_new)

            # Fetch existing data
            df_old = pd.read_sql(f'SELECT * FROM "{self.table_name}"', self.conn, index_col='Date')
            
            # Combine old and new data for rolling metrics
            df_combined = pd.concat([df_old.iloc[-(window-1):], df_new])
            df_combined = self._calc_rolling_metrics(df_combined, window)
            
            # Get the newly calculated rows
            new_rows = df_combined.iloc[window-1:]
            
            # Append new rows to old data
            df_updated = pd.concat([df_old, new_rows])
            
            # Recalculate signals and PnL on the full dataframe
            self.df = self._calc_signals_pnl(df_updated, entry, exit, sl, p_th, corr_th, window)
            
            # Overwrite the old table with the updated data
            self._write_to_sql()

            # Update pair_plots
            self.conn.execute(f'DELETE FROM "pair_plots" WHERE name = "{self.table_name}"')
            self.conn.commit()
            self._plot_positions(self.df, entry, exit, sl, p_th, corr_th, window)

            
            self.conn.commit()
            print(f"Pair {self.table_name} updated successfully.")
        else:
            print("Pair data is up to date.")

        self.conn.close()