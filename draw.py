import json
import requests
import folium
import pandas as pd
from collections import defaultdict
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import islice
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import shelve


# Define a custom exception for failed API calls
class ASNInfoError(Exception):
    pass


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=10),
       retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError, ASNInfoError)))
def fetch_asn_info_from_api(asn):
    """Fetch ASN location and country information from the API with timeout and retry."""
    url = f'https://api.asrank.caida.org/v2/restful/asns/{asn}'
    try:
        response = requests.get(url, timeout=10)  # Set timeout to 10 seconds
        response.raise_for_status()
        data = response.json()
        return data['data']['asn']
    except requests.HTTPError as e:
        raise ASNInfoError(f"Failed to fetch ASN info for {asn}") from e


def get_asn_info(asn, cache):
    """Fetch ASN info with caching."""
    if asn in cache:
        return cache[asn]

    asn_info = fetch_asn_info_from_api(asn)
    cache[asn] = asn_info
    return asn_info


def filter_asn_info(asn, count, cache):
    """Filter function to process ASN info with caching."""
    try:
        asn_info = get_asn_info(asn, cache)
        if asn_info['country']['iso'] == 'US':
            return asn, {
                'count': count,
                'longitude': asn_info['longitude'],
                'latitude': asn_info['latitude']
            }
    except Exception as e:
        print(f"Could not process ASN {asn}: {e}")
    return None


def filter_us_asns(asn_counts, cache):
    """Filter ASNs to include only those located in the US using multi-threading and caching."""
    us_asns = {}
    asn_counts = dict(islice(asn_counts.items(), 3000))
    with ThreadPoolExecutor(max_workers=10) as executor:  # Adjust max_workers as needed
        future_to_asn = {executor.submit(filter_asn_info, asn, count, cache): asn for asn, count in asn_counts.items()}
        for future in tqdm(as_completed(future_to_asn), total=len(asn_counts), desc="Processing ASNs"):
            result = future.result()
            if result:
                asn, info = result
                us_asns[asn] = info
    return us_asns

# def filter_us_asns(asn_counts):
#     """Filter ASNs to include only those located in the US."""
#     us_asns = {}
#     cnt = 0
#     for asn, count in tqdm(asn_counts.items(), desc="Processing ASNs"):
#         if cnt == 100:
#             break
#         asn_info = get_asn_info(asn)
#         if asn_info['country']['iso'] == 'US':
#             us_asns[asn] = {
#                 'count': count,
#                 'longitude': asn_info['longitude'],
#                 'latitude': asn_info['latitude']
#             }
#             print(cnt)
#             cnt += 1
#     return us_asns


def create_heatmap(us_asns):
    """Create a heatmap on a US map based on ASN locations."""
    m = folium.Map(location=[37.0902, -95.7129], zoom_start=5, tiles='cartodbpositron')  # Centered on USA
    heat_data = [[info['latitude'], info['longitude'], info['count']] for info in us_asns.values()]

    from folium.plugins import HeatMap
    HeatMap(heat_data).add_to(m)


    # Save map to an HTML file
    m.save("us_asn_heatmap.html")
    print("Heatmap saved to us_asn_heatmap.html")

def main():
    # Load the ASN updates from the saved file
    with open('asn_updates.json', 'r') as f:
        asn_counts = json.load(f)
        asn_counts = {k: v for k, v in sorted(asn_counts.items(), key=lambda item: item[1], reverse=True)}
        print(asn_counts)
        # Open a shelf for caching ASN data
        with shelve.open('asn_cache.db') as cache:
            # Filtering US ASNs using cache to reduce API requests
            us_asns = filter_us_asns(asn_counts, cache)
            create_heatmap(us_asns)

if __name__ == "__main__":
    main()