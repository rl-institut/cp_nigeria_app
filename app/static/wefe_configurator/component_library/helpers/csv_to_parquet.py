import pandas as pd
from pathlib import Path

for csv_path in Path(".").glob("*.csv"):
    parquet_path = csv_path.with_suffix(".parquet")
    df = pd.read_csv(csv_path)
    df.to_parquet(parquet_path, compression="snappy")
    print(f"Converted {csv_path} to {parquet_path}")
