import io, matplotlib.pyplot as plt
import sqlite3

pair_name = 'SBICARD_BAJFINANCE'
conn = sqlite3.connect('pair_trading.db')
blob = conn.execute("""
SELECT plot FROM pair_plots WHERE name = ?""", (pair_name,)).fetchone()[0]
buf = io.BytesIO(blob)
conn.close()
plt.figure(figsize=(10, 6))
plt.imshow(plt.imread(buf), aspect='auto')
plt.axis('off')
plt.title(pair_name)
plt.show()
