import pandas as pd

file_path = r"d:\新训\第一周\社区侦探项目\社区侦探项目-AI打标.xlsx"
try:
    df = pd.read_excel(file_path)
    print("Columns:", df.columns.tolist())
    print("First row:", df.iloc[0].to_dict())
except Exception as e:
    print(f"Error reading excel: {e}")
