import sqlite3
import pandas as pd
import matplotlib.pyplot as plt

def plot_cumulative_pnl():
    """
    Connects to the pair_trading.db, reads the all_trades table,
    and plots the cumulative PnL over time.
    """
    conn = sqlite3.connect('pair_trading.db')
    
    try:
        df = pd.read_sql_query("SELECT * FROM all_trades", conn)
    except pd.io.sql.DatabaseError:
        print("The 'all_trades' table does not exist. Please run the main script to generate it.")
        return

    if df.empty:
        print("The 'all_trades' table is empty. No data to plot.")
        return

    df['start'] = pd.to_datetime(df['start'])
    df = df.sort_values(by='start')
    df['cumulative_pnl'] = df['pnl'].cumsum()

    plt.figure(figsize=(12, 6))
    plt.plot(df['start'], df['cumulative_pnl'], linestyle='-')
    plt.xlabel('Date')
    plt.ylabel('Cumulative PnL')
    plt.title('Cumulative PnL Over Time')
    plt.grid(True)
    
    plt.savefig('cumulative_pnl.png')
    print("Plot saved to cumulative_pnl.png")

if __name__ == "__main__":
    plot_cumulative_pnl()
