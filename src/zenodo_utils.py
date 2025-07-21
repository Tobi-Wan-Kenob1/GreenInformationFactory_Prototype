# src/zenodo_utils.py

import os
import requests
import pandas as pd

def download_zenodo_file(record_id: str, filename: str, dest_folder: str = "data") -> pd.DataFrame:
    """
    Downloads a file from a Zenodo record and loads it as a pandas DataFrame.
    
    Parameters:
        record_id (str): Zenodo record ID (e.g. '16256961')
        filename (str): Name of the file in the record (e.g. 'raw_data.csv')
        dest_folder (str): Local folder to save the file
    
    Returns:
        pd.DataFrame: The loaded data as a pandas DataFrame
    """
    os.makedirs(dest_folder, exist_ok=True)
    local_path = os.path.join(dest_folder, filename)
    
    if not os.path.exists(local_path):
        print(f"🔽 Downloading '{filename}' from Zenodo record {record_id}...")
        url = f"https://zenodo.org/records/{record_id}/files/{filename}?download=1"
        response = requests.get(url)
        if response.status_code != 200:
            raise Exception(f"Failed to download file: {response.status_code} - {response.text}")
        with open(local_path, 'wb') as f:
            f.write(response.content)
        print(f"✅ File downloaded and saved to '{local_path}'")
    else:
        print(f"📁 Using cached file: {local_path}")
    
    return pd.read_csv(local_path)
