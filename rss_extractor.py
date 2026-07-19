import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

PODCAST_ID = "280789489"
DEFAULT_FEED_URL = "https://feeds.redcircle.com/6fb1e853-719d-44d9-8b9e-9d4af81d7a89"

def get_feed_url():
    """Fetch the latest feed URL from iTunes API, falling back to default if lookup fails."""
    lookup_url = f"https://itunes.apple.com/lookup?id={PODCAST_ID}"
    try:
        req = urllib.request.Request(lookup_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        if data.get('resultCount', 0) > 0:
            feed_url = data['results'][0].get('feedUrl')
            if feed_url:
                return feed_url
    except Exception as e:
        print(f"Warning: iTunes lookup failed ({e}). Using default feed URL.")
    return DEFAULT_FEED_URL

def fetch_rss_data(feed_url):
    """Fetch raw RSS feed XML content."""
    req = urllib.request.Request(feed_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return response.read()

def parse_rss_xml(xml_data):
    """Parse raw XML data into an ElementTree Element object."""
    return ET.fromstring(xml_data)

def parse_item_date(item):
    """Extract and format the publication date from an RSS item."""
    pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
    if not pub_date:
        return None
    try:
        dt = parsedate_to_datetime(pub_date)
        dt_pacific = dt.astimezone(ZoneInfo("America/Los_Angeles"))
        return dt_pacific.strftime("%Y-%m-%d")
    except Exception:
        return None

def filter_episodes(xml_root, target_date=None, start_date=None, end_date=None):
    """Filter and parse RSS items from XML root into structured episode dicts."""
    items = xml_root.findall('.//item')
    if not items:
        raise ValueError("No episodes found in RSS feed.")
    
    matched_items = []
            
    if target_date:
        for item in items:
            p_date = parse_item_date(item)
            if p_date == target_date:
                matched_items.append(item)
                break
            else:
                pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
                if target_date in pub_date:
                    matched_items.append(item)
                    break
        if not matched_items:
            raise ValueError(f"No episode found in RSS feed for date: {target_date}")
            
    elif start_date or end_date:
        s_date = start_date if start_date else "1970-01-01"
        e_date = end_date if end_date else "9999-12-31"
        
        for item in items:
            p_date = parse_item_date(item)
            if p_date and s_date <= p_date <= e_date:
                matched_items.append(item)
        if not matched_items:
            raise ValueError(f"No episodes found in RSS feed for range: {start_date} to {end_date}")
            
    else:
        matched_items.append(items[0])
        
    episodes = []
    for item in matched_items:
        title = item.find('title').text if item.find('title') is not None else "No Title"
        description = ""
        desc_elem = item.find('description')
        if desc_elem is not None:
            description = desc_elem.text or ""
        encoded_elem = item.find('{http://purl.org/rss/1.0/modules/content/}encoded')
        if encoded_elem is not None:
            description = encoded_elem.text or description
            
        pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
        p_date = parse_item_date(item) or pub_date
        
        vtt_url = None
        transcript_elem = item.find('{https://podcastindex.org/namespace/1.0}transcript')
        if transcript_elem is not None:
            vtt_url = transcript_elem.attrib.get('url')
            
        episodes.append({
            'title': title,
            'description': description,
            'pub_date': pub_date,
            'date_str': p_date,
            'vtt_url': vtt_url
        })
        
    return episodes

def parse_rss_feed(feed_url, target_date=None, start_date=None, end_date=None):
    """Fetch and parse RSS feed, returning details for matched episode(s)."""
    xml_data = fetch_rss_data(feed_url)
    root = parse_rss_xml(xml_data)
    return filter_episodes(root, target_date=target_date, start_date=start_date, end_date=end_date)
