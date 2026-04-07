import pandas as pd
from momentum_tracker import process_file, generate_html
import os

# Create a mini version of the CSV for testing
df = pd.read_csv("market cap greater than 10000.csv").head(5)
df.to_csv("test_market_cap.csv", index=False)

print("Starting quick test with 5 stocks...")

# Run the processing on the test file
# Note: I'll manually call the functions to avoid the input() prompt
results_df = process_file("test_market_cap.csv")
generate_html(results_df, "test_momentum_report.html")

print("\nTest complete! You can now check 'test_momentum_report.html'")
# Clean up test csv
os.remove("test_market_cap.csv")
