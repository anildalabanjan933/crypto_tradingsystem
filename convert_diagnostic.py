import pandas as pd
from datetime import datetime

# Read the diagnostic CSV
df = pd.read_csv('diagnostic_bearish.csv')

# Convert Unix timestamp to readable datetime
df['Timestamp_Readable'] = pd.to_datetime(df['Timestamp'], unit='s')

# Save with readable timestamps
df.to_csv('diagnostic_bearish_readable.csv', index=False)

print("Converted diagnostic report saved to diagnostic_bearish_readable.csv")
print("\nFirst 10 entry signals:")
print(df[['Timestamp_Readable', 'Column_End_Level', 'ADX', 'Double_Bottom', 'Entry_Signal']].head(10))
