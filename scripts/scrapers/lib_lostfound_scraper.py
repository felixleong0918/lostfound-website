import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

def scrape_lost_and_found(base_url, max_pages):
    # The headers based on your provided HTML
    headers = ["編號", "拾獲日期", "拾獲地點", "外觀描述", "物品分類", "存放地點"]
    all_extracted_data = []

    for page in range(max_pages):
        print(f"Scraping page {page}...")
        
        # Build the URL parameters
        params = {'q': 'viewer', 'page': page}
        response = requests.get(base_url, params=params)
        
        # Stop if we hit a bad response
        if response.status_code != 200:
            print(f"Failed to retrieve page {page}. Status Code: {response.status_code}")
            break

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # In Drupal views, the data is usually in a table body
        rows = soup.select('table tbody tr')
        
        # If there are no rows, we've likely hit the end of the pagination
        if not rows:
            print("No more data found. Stopping crawler.")
            break

        for row in rows:
            # Find all table data cells in the row
            cols = row.find_all('td')
            
            # Ensure we have the correct number of columns before extracting
            if len(cols) >= 6:
                row_data = [
                    cols[0].text.strip(),  # 編號
                    cols[1].text.strip(),  # 拾獲日期
                    cols[2].text.strip(),  # 拾獲地點
                    cols[3].text.strip(),  # 外觀描述
                    cols[4].text.strip(),  # 物品分類
                    cols[5].text.strip()   # 存放地點
                ]
                all_extracted_data.append(row_data)
        
        # Be polite to the server to avoid getting IP blocked
        time.sleep(7)

    # Convert to DataFrame and export
    df = pd.DataFrame(all_extracted_data, columns=headers)
    df.to_csv('training_data.csv', index=False, encoding='utf-8-sig')
    print(f"Scraping complete! Saved {len(df)} records to training_data.csv")

if __name__ == "__main__":
    TARGET_URL = "https://lostfound.lib.ntu.edu.tw/"
    scrape_lost_and_found(TARGET_URL, max_pages=55)
