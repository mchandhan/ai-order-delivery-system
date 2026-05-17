import pandas as pd
import sqlite3
import os
import time

file_path = r"C:\Users\mchan\Downloads\Online Retail.xlsx"
db_path = os.path.join(os.path.dirname(__file__), "orders.db")

def bulk_import():
    if not os.path.exists(file_path):
        print("Error: File not found.")
        return

    print("Reading Excel file (this may take a minute)...")
    start_time = time.time()
    df = pd.read_excel(file_path)
    print(f"Read {len(df)} rows in {time.time() - start_time:.2f}s")

    # Clean and Map Data
    print("Cleaning data...")
    df = df.dropna(subset=['Description'])
    
    # Map to our schema
    import_df = pd.DataFrame({
        'part': df['Description'].astype(str).str.strip(),
        'material': 'Not specified',
        'quantity': df['Quantity'].fillna(0).astype(int),
        'deadline': pd.to_datetime(df['InvoiceDate']).dt.strftime('%Y-%m-%d'),
        'status': 'Completed'
    })

    # Connect to DB
    conn = sqlite3.connect(db_path)
    
    print("Importing to database...")
    import_df.to_sql('orders', conn, if_exists='append', index=False)
    
    print("Creating indexes for performance...")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_id ON orders(order_id DESC)")
    
    conn.commit()
    conn.close()
    
    print(f"SUCCESS: Imported {len(import_df)} rows in total!")
    print(f"Total time: {time.time() - start_time:.2f}s")

if __name__ == "__main__":
    bulk_import()
