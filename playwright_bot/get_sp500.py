import io
import urllib.request
import pandas as pd

# Wikipedia requires a browser User-Agent
url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

html_bytes = urllib.request.urlopen(req).read()
tables = pd.read_html(io.BytesIO(html_bytes))
table = tables[0]

# Save company names
table['Security'].to_csv('sp500_companies.csv', index=False, header=['Company Name'])
print(f"Successfully saved {len(table)} company names to sp500_companies.csv!")
