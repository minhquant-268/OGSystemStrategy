from src.utils.connection.db_connect import engine
from sqlalchemy import text
import pandas as pd

def explore():
    with engine.connect() as conn:
        print("--- Tables in dbo schema ---")
        res = conn.execute(text("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'dbo'"))
        tables = [row[0] for row in res]
        print(tables)
        
        for table in ["assets", "providers"]:
            if table in tables:
                print(f"\n--- Columns in dbo.{table} ---")
                res = conn.execute(text(f"SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{table}' AND TABLE_SCHEMA = 'dbo'"))
                for row in res:
                    print(row)
                
                print(f"\n--- Sample data from dbo.{table} ---")
                res = conn.execute(text(f"SELECT TOP 3 * FROM dbo.{table}"))
                df = pd.DataFrame(res.fetchall(), columns=res.keys())
                print(df)

if __name__ == "__main__":
    explore()
