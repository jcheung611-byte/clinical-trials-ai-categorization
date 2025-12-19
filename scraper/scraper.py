import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
from typing import List, Dict


def scrape_clinicaltrials_locations(nct_id: str) -> tuple:
    """
    Scrape location information from a ClinicalTrials.gov study.
    
    Args:
        nct_id: The NCT identifier (e.g., 'NCT06179160')
    
    Returns:
        Tuple of (trial_name, central_contacts, locations_list)
        - trial_name: Official title of the study
        - central_contacts: Dict with study-level contact info
        - locations_list: List of dictionaries containing location information
    """
    
    # Try API v2 first
    api_url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
    
    try:
        print(f"Attempting to fetch data via API for {nct_id}...")
        response = requests.get(api_url)
        
        if response.status_code == 200:
            data = response.json()
            trial_name = extract_trial_name(data)
            central_contacts = extract_central_contacts(data)
            locations = extract_locations_from_api(data)
            if locations:
                print(f"Successfully retrieved {len(locations)} locations via API")
                return trial_name, central_contacts, locations
        else:
            print(f"API returned status code {response.status_code}, falling back to web scraping...")
    except Exception as e:
        print(f"API request failed: {e}, falling back to web scraping...")
    
    # Fallback to web scraping
    empty_contacts = {
        'study_contact_name': '',
        'study_contact_phone': '',
        'study_contact_email': '',
        'study_contact_backup_name': '',
        'study_contact_backup_phone': '',
        'study_contact_backup_email': '',
    }
    return '', empty_contacts, scrape_locations_from_html(nct_id)


def extract_trial_name(data: dict) -> str:
    """Extract the official trial title from API response."""
    try:
        protocol_section = data.get('protocolSection', {})
        identification = protocol_section.get('identificationModule', {})
        # Try official title first, then brief title
        title = identification.get('officialTitle', '')
        if not title:
            title = identification.get('briefTitle', '')
        return title
    except Exception:
        return ''


def extract_central_contacts(data: dict) -> dict:
    """Extract central/study-level contacts from API response."""
    try:
        protocol_section = data.get('protocolSection', {})
        contacts_locations = protocol_section.get('contactsLocationsModule', {})
        central_contacts = contacts_locations.get('centralContacts', [])
        
        result = {
            'study_contact_name': '',
            'study_contact_phone': '',
            'study_contact_email': '',
            'study_contact_backup_name': '',
            'study_contact_backup_phone': '',
            'study_contact_backup_email': '',
        }
        
        if central_contacts and len(central_contacts) > 0:
            # Primary study contact
            primary = central_contacts[0]
            result['study_contact_name'] = primary.get('name', '')
            result['study_contact_phone'] = primary.get('phone', '')
            result['study_contact_email'] = primary.get('email', '')
            
            # Backup study contact (if exists)
            if len(central_contacts) > 1:
                backup = central_contacts[1]
                result['study_contact_backup_name'] = backup.get('name', '')
                result['study_contact_backup_phone'] = backup.get('phone', '')
                result['study_contact_backup_email'] = backup.get('email', '')
        
        return result
    except Exception:
        return {
            'study_contact_name': '',
            'study_contact_phone': '',
            'study_contact_email': '',
            'study_contact_backup_name': '',
            'study_contact_backup_phone': '',
            'study_contact_backup_email': '',
        }


def extract_locations_from_api(data: dict) -> List[Dict[str, str]]:
    """Extract locations and contact information from API response."""
    locations = []
    
    try:
        # Navigate through the API response structure
        protocol_section = data.get('protocolSection', {})
        contacts_locations = protocol_section.get('contactsLocationsModule', {})
        location_list = contacts_locations.get('locations', [])
        
        for loc in location_list:
            location_info = {
                'institution': loc.get('facility', 'N/A'),
                'city': loc.get('city', 'N/A'),
                'state': loc.get('state', 'N/A'),
                'zip': loc.get('zip', ''),
                'country': loc.get('country', 'N/A')
            }
            
            # Extract contact information if available
            contacts = loc.get('contacts', [])
            
            # Store all contacts as a list for flexible processing later
            location_info['all_contacts'] = contacts
            
            if contacts and len(contacts) > 0:
                # First contact gets separate columns
                first_contact = contacts[0]
                location_info['contact_name'] = first_contact.get('name', '')
                location_info['contact_phone'] = first_contact.get('phone', '')
                location_info['contact_email'] = first_contact.get('email', '')
                
                # Second contact gets separate columns
                if len(contacts) > 1:
                    second_contact = contacts[1]
                    location_info['contact_2_name'] = second_contact.get('name', '')
                    location_info['contact_2_phone'] = second_contact.get('phone', '')
                    location_info['contact_2_email'] = second_contact.get('email', '')
                else:
                    location_info['contact_2_name'] = ''
                    location_info['contact_2_phone'] = ''
                    location_info['contact_2_email'] = ''
                
                # Third+ contacts go into Contact 3 column (condensed)
                if len(contacts) > 2:
                    additional_contacts = []
                    for contact in contacts[2:]:
                        name = contact.get('name', '')
                        phone = contact.get('phone', '')
                        email = contact.get('email', '')
                        contact_str = f"{name} | {phone} | {email}".strip()
                        additional_contacts.append(contact_str)
                    location_info['contact_3'] = ' || '.join(additional_contacts)
                else:
                    location_info['contact_3'] = ''
            else:
                # No contacts available
                location_info['contact_name'] = ''
                location_info['contact_phone'] = ''
                location_info['contact_email'] = ''
                location_info['contact_2_name'] = ''
                location_info['contact_2_phone'] = ''
                location_info['contact_2_email'] = ''
                location_info['contact_3'] = ''
            
            locations.append(location_info)
    except Exception as e:
        print(f"Error extracting from API response: {e}")
        return []
    
    return locations


def scrape_locations_from_html(nct_id: str) -> List[Dict[str, str]]:
    """Scrape locations from the HTML page."""
    url = f"https://clinicaltrials.gov/study/{nct_id}"
    
    print(f"Scraping from {url}...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        locations = []
        
        # Find the locations section
        # The structure may vary, so we'll try multiple approaches
        
        # Approach 1: Look for specific location elements
        location_elements = soup.find_all('div', {'class': lambda x: x and 'location' in x.lower()})
        
        if not location_elements:
            # Approach 2: Look for table rows or list items containing location data
            location_elements = soup.find_all(['tr', 'li'], string=lambda x: x and any(
                term in str(x).lower() for term in ['hospital', 'clinic', 'medical center', 'healthcare', 'university']
            ))
        
        # Try to parse the locations
        for elem in location_elements:
            location_info = parse_location_element(elem)
            if location_info:
                locations.append(location_info)
        
        if locations:
            print(f"Successfully scraped {len(locations)} locations from HTML")
        else:
            print("No locations found in HTML. The page structure may have changed.")
            print("Saving HTML for manual inspection...")
            with open(f'{nct_id}_page.html', 'w', encoding='utf-8') as f:
                f.write(response.text)
        
        return locations
        
    except Exception as e:
        print(f"Error scraping HTML: {e}")
        return []


def parse_location_element(element) -> Dict[str, str]:
    """Parse a location element to extract institution, city, state, country."""
    try:
        text = element.get_text(strip=True)
        # This is a simplified parser - actual implementation will depend on the HTML structure
        # We'll need to inspect the actual page to write the correct parser
        
        location_info = {
            'institution': 'N/A',
            'city': 'N/A',
            'state': 'N/A',
            'country': 'N/A',
            'raw_text': text
        }
        
        return location_info
    except:
        return None


def save_locations(locations: List[Dict[str, str]], nct_id: str, format: str = 'csv'):
    """Save locations to a file."""
    if not locations:
        print("No locations to save.")
        return
    
    df = pd.DataFrame(locations)
    
    if format == 'csv':
        filename = f'{nct_id}_locations.csv'
        df.to_csv(filename, index=False)
        print(f"Saved {len(locations)} locations to {filename}")
    elif format == 'json':
        filename = f'{nct_id}_locations.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(locations, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(locations)} locations to {filename}")
    elif format == 'excel':
        filename = f'{nct_id}_locations.xlsx'
        df.to_excel(filename, index=False)
        print(f"Saved {len(locations)} locations to {filename}")


if __name__ == "__main__":
    # Example usage
    nct_id = "NCT06179160"
    
    locations = scrape_clinicaltrials_locations(nct_id)
    
    if locations:
        print(f"\nFound {len(locations)} locations:")
        print("-" * 80)
        for i, loc in enumerate(locations, 1):
            print(f"\n{i}. {loc.get('institution', 'N/A')}")
            print(f"   City: {loc.get('city', 'N/A')}")
            print(f"   State: {loc.get('state', 'N/A')}")
            print(f"   Country: {loc.get('country', 'N/A')}")
        
        # Save to CSV
        save_locations(locations, nct_id, format='csv')
        save_locations(locations, nct_id, format='json')
    else:
        print("\nNo locations found. Please check the NCT ID or try again later.")

