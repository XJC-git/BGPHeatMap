import json
import os
import requests
import subprocess
from collections import defaultdict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

def download_mrt_file(url, local_file):
    """Helper function to download a single MRT file."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        with open(local_file, 'wb') as file:
            file.write(response.content)
        print(f"Successfully downloaded {url}")
    except requests.exceptions.RequestException as e:
        print(f"Failed to download {url}: {e}")
    return local_file

def download_mrt_files_for_date(date, rrc_list, download_dir):
    """Download all MRT files for a given date and list of RRCs."""
    base_url = "https://data.ris.ripe.net/"
    date_obj = datetime.strptime(date, '%Y%m%d')
    formatted_date = date_obj.strftime('%Y.%m')
    os.makedirs(download_dir, exist_ok=True)

    urls = []
    for rrc in rrc_list:
        for hour in range(24):
            for minute in range(0, 60, 5):
                formatted_hour = f"{hour:02}"
                formatted_minute = f"{minute:02}"
                url = f"{base_url}rrc{rrc}/{formatted_date}/updates.{date}.{formatted_hour}{formatted_minute}.gz"
                local_file = os.path.join(download_dir, f"rrc{rrc}_updates_{date}{formatted_hour}{formatted_minute}.gz")
                urls.append((url, local_file))

    return urls

def download_all_mrt_files(dates, rrc_list, download_dir):
    """Download MRT files concurrently for multiple dates."""
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = []
        for date in dates:
            urls = download_mrt_files_for_date(date, rrc_list, download_dir)
            for url, local_file in urls:
                futures.append(executor.submit(download_mrt_file, url, local_file))

        for future in as_completed(futures):
            future.result()

def run_bgpdump_on_file(file_path):
    """Run bgpdump on the given MRT file and return its output as a string."""
    try:
        process = subprocess.run(['bgpdump', '-m', file_path], check=True, stdout=subprocess.PIPE, universal_newlines=True)
        return process.stdout
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while running bgpdump: {e}")
        return ''

def parse_bgpdump_output(output):
    """Parse the bgpdump output and count updates per ASN."""
    asn_count = defaultdict(int)
    for line in output.splitlines():
        parts = line.split('|')
        if len(parts) < 7:
            continue
        as_path = parts[6]
        if as_path:
            # Get the last ASN in the AS path which represents the origin ASN
            origin_asn = as_path.split()[-1]
            asn_count[origin_asn] += 1
    return dict(asn_count)

def main(dates, rrc_list):
    download_dir = './dataset'  # Define the directory to store downloaded MRT files
    download_all_mrt_files(dates, rrc_list, download_dir)

    total_asn_count = defaultdict(int)
    for root, _, files in os.walk(download_dir):
        for mrt_file in files:
            if mrt_file.endswith('.gz'):
                full_path = os.path.join(root, mrt_file)
                output = run_bgpdump_on_file(full_path)
                file_asn_count = parse_bgpdump_output(output)
                for asn, count in file_asn_count.items():
                    total_asn_count[asn] += count

    return dict(total_asn_count)

if __name__ == "__main__":
    dates = ['20241101']  # Example dates
    rrcs = [f'{i:02}' for i in range(0, 1)]  # Example RRCs from RRC00 to RRC25
    asn_updates = main(dates, rrcs)
    with open('asn_updates.json', 'w') as f:
        json.dump(asn_updates, f)
