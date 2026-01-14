import datetime as dt
import sqlite3
import numpy as np
import pandas as pd
import yfinance as yf

class Ticker:
    def __init__(self, ticker: pd.core.series.Series):
        self.sector     = ticker.Sector
        self.symbol     = ticker.Symbol
        self.lot_size   = ticker.LotSize
        self.conn       = sqlite3.connect('pair_trading.db', timeout=30)
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.table_name = self.symbol

        # 1) Does table exist?
        exists = self.conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name=?",
            (self.table_name,)
        ).fetchone()

        if exists:
            # 2) Load existing data
            existing = pd.read_sql_query(
                f'SELECT * FROM "{self.table_name}"',
                self.conn,
                parse_dates=['Date'],
                index_col='Date'
            )

            # 3) Check if the last date matches today
            last_date = existing.index.max().date() 
            today     = dt.datetime.now().date() - dt.timedelta(days=1)
            if today.weekday() in [5, 6]:
                # if today is Saturday or Sunday, adjust to Friday
                today -= dt.timedelta(days=today.weekday() - 4)
            if last_date < today:
                # there's at least one missing day: download from the next calendar day
                start_date = last_date + dt.timedelta(days=1)
                print(f"Found data through {last_date}, "
                      f"downloading from {start_date} to {today}…")

                new_df = yf.download(
                    f"{self.symbol}.NS",
                    start=start_date,
                    end=dt.datetime.now(),
                    auto_adjust=True
                )
                if not new_df.empty:
                    # compute log returns (shifted on the new_df itself)
                    # new_df['LogReturns'] = np.log(
                    #     new_df['Close'] / new_df['Close'].shift(1)
                    # )

                    # flatten MultiIndex columns if present
                    if isinstance(new_df.columns, pd.MultiIndex):
                        new_df.columns = new_df.columns.get_level_values(0)

                    new_df.index.name = 'Date'

                    # append to SQL table
                    new_df.to_sql(
                        self.table_name,
                        self.conn,
                        if_exists='append',
                        index=True
                    )

                    # stitch old + new together for in‐memory df
                    self.df = pd.concat([existing, new_df])
                else:
                    # no new rows found (e.g. weekend/holiday), keep existing
                    self.df = existing
            else:
                # already up to date
                print(f"{self.symbol} data is already current through {last_date}.")
                self.df = existing

        else:
            # Table doesn’t exist yet—download full history
            print(f"Downloading full history for {self.symbol}…")
            full = yf.download(
                f"{self.symbol}.NS",
                start=dt.datetime.now() - dt.timedelta(days=365*10),
                end=dt.datetime.now(),
                auto_adjust=True
            )
            # full['LogReturns'] = np.log(full['Close'] / full['Close'].shift(1))

            if isinstance(full.columns, pd.MultiIndex):
                full.columns = full.columns.get_level_values(0)

            full.index.name = 'Date'
            full.to_sql(self.table_name, self.conn,
                        if_exists='replace', index=True)
            self.df = full

        # clean up
        self.conn.close()
