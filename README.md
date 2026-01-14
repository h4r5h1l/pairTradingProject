# Pair Trading Project

**Overview**

This repository implements a lightweight pair-trading backtesting toolkit focused on Indian NSE equities. It downloads historical price data (via `yfinance`), stores per-ticker time series in a local SQLite database, generates pair-level backtests using rolling OLS residuals and ADF stationarity checks, and persists per-pair plots and aggregate trade records.

**Features**

- **Per-ticker storage:** stores raw adjusted price history for each symbol in `pair_trading.db`.
- **Pair backtests:** produces per-pair tables named as `Y_X` with rolling regression metrics, z-scores, entry/exit signals, and PnL.
- **Plot storage:** saves pair diagnostic plots (PNG blobs) in the database table `pair_plots`.
- **Aggregate trades:** builds an `all_trades` table summarizing individual trade entries/exits and PnL.
- **Utilities:** scripts to plot cumulative PnL and view individual pair plots.

**Requirements**

- Python 3.10+ (see `pyproject.toml` for declared dependencies)
- Packages: see `requirements.txt` (pandas, numpy, matplotlib, statsmodels, yfinance)

Install dependencies (recommended inside a virtualenv):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Configuration**

- The script expects `nse_fno_lots.csv` in the project root. This CSV must contain at least the columns: `Symbol`, `LotSize`, and `Sector`.
- The SQLite database file used is `pair_trading.db` (created automatically by the scripts).

**Quick Usage**

- Populate/update per-ticker tables and generate all pair backtests (this is CPU-heavy):

```bash
python main.py
```

- Create `all_trades` summary table and check open positions (these functions are also invoked by `main.py`):

```bash
# run from Python or call scripts that wrap these functions
python -c "from all_pairs import create_trades_table, get_open_positions; create_trades_table(); get_open_positions()"
```

- Plot aggregate cumulative PnL (reads `all_trades` and writes `cumulative_pnl.png`):

```bash
python plot_pnl.py
```

- View a saved pair plot (edit the `pair_name` variable in `show_plot.py` then run):

```bash
python show_plot.py
```

**Database schema (high level)**

- Per-ticker tables: one table per symbol (table name = symbol). Each table stores price history with a `Date` index.
- Per-pair tables: named `Y_X` and contain rolling regression results, `Position`, `PnL`, `Cumulative_PnL`, `Drawdown` and related columns.
- `pair_plots`: stores (name, plot blob, Cumulative_PnL, Max_Drawdown, Sector, n_Longs, n_Shorts, n_Trades, n_Profits, n_Losses).
- `all_trades`: summarized trade records created by `create_trades_table()`.

**Important Files**

- `main.py`: orchestrates ticker downloads (via `Ticker`), launches per-pair backtests in parallel, and builds `all_trades`.
- `ticker.py`: handles downloading and maintaining per-symbol tables in `pair_trading.db` using `yfinance`.
- `pair.py`: core Pair class — computes rolling OLS, residual z-scores, ADF p-values, entry/exit signals, PnL calculation, and persists plots.
- `all_pairs.py`: helpers to scan pair tables, summarize trades into `all_trades`, and report open positions.
- `plot_pnl.py`: plots cumulative PnL from `all_trades`.
- `show_plot.py`: quick utility to display a stored pair plot from `pair_plots`.
- `nse_fno_lots.csv`: expected input mapping symbols to lot sizes and sectors.

**Testing / Examples**

- Simple scripts are provided to exercise functionality:
  - `test_pair.py`: example that downloads tickers and runs a `Pair` for two sample symbols (will write to the DB and open a plot).
  - `test_stats.py`: exploratory script to compute metrics over parameter ranges.

Run tests/examples directly (ensure dependencies and `nse_fno_lots.csv` are present):

```bash
python test_pair.py
python test_stats.py
```

**Notes & Caveats**

- `yfinance` can be rate-limited when downloading many symbols; throttle or stagger downloads when running `main.py` for large universes.
- `main.py` uses multiprocessing to parallelize pair processing; expect high CPU and significant database writes.
- The project uses SQLite for convenience; concurrent writes are enabled via `PRAGMA journal_mode = WAL;` but monitor for contention on very large runs.
- `pyproject.toml` currently declares `requires-python = ">=3.13"` — if your environment uses an earlier 3.x, adjust or ignore this constraint as appropriate.

**License**

This repository contains code snippets and utilities for private use. No license file is included; add a license if you plan to publish or share widely.

---

If you'd like, I can also:

- run a quick smoke test using a single symbol pair, or
- adjust README wording or add examples showing how to customize pair parameters.
