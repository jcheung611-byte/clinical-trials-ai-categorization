#!/usr/bin/env python3
"""
Scrape locations for net new trials from 12/16/2024 search.
Uses the existing scraper format for center-level data.
Includes Institution_clean column with fuzzy matching normalization.
"""

import sys
import requests
import pandas as pd
import time
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from difflib import SequenceMatcher

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)


BASE_URL = "https://clinicaltrials.gov/api/v2/studies"


# ==============================================================================
# INSTITUTION NORMALIZATION LOGIC
# ==============================================================================

def normalize_institution_name(name: str) -> str:
    """Normalize institution name by removing site numbers, extra spaces, and standardizing punctuation."""
    if not name or name == 'N/A':
        return name
    
    # Remove site numbers like "( Site 1007)" or "(Site 1007)"
    normalized = re.sub(r'\s*\(\s*Site\s+\d+\s*\)', '', name, flags=re.IGNORECASE)
    
    # Remove extra parentheses with location info like "(Boston)"
    normalized = re.sub(r'\s*\([^)]*\)\s*', ' ', normalized)
    
    # Normalize hyphens and dashes
    normalized = normalized.replace('–', '-').replace('—', '-')
    
    # Remove extra spaces
    normalized = ' '.join(normalized.split())
    
    return normalized.strip()


def similarity_ratio(str1: str, str2: str) -> float:
    """Calculate similarity ratio between two strings."""
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def extract_institution_keywords(name: str) -> set:
    """Extract distinctive keywords from an institution name."""
    n = name.lower().strip()
    
    key_identifiers = [
        # MAJOR CANCER CENTERS
        ('banner md anderson', 'banner'), ('banner health', 'banner'),
        ('md anderson', 'mdanderson'), ('m.d. anderson', 'mdanderson'),
        ('memorial sloan kettering', 'msk'), ('memorial sloan-kettering', 'msk'),
        ('sloan kettering', 'msk'), ('sloan-kettering', 'msk'),
        ('dana farber', 'danafarber'), ('dana-farber', 'danafarber'),
        ('mayo clinic', 'mayo'),
        ('sidney kimmel', 'hopkins'), ('johns hopkins', 'hopkins'), ('john hopkins', 'hopkins'),
        ('cedars-sinai', 'cedarssinai'), ('cedars sinai', 'cedarssinai'),
        ('moffitt', 'moffitt'), ('city of hope', 'cityofhope'),
        ('cleveland clinic', 'clevelandclinic'), ('huntsman', 'huntsman'),
        ('fred hutchinson', 'fredhutch'), ('roswell park', 'roswellpark'),
        # RESEARCH NETWORKS
        ('sarah cannon', 'sarahcannon'), ('scri oncology', 'sarahcannon'),
        ('south texas accelerated', 'start'), ('start san antonio', 'start'),
        ('start midwest', 'start'), ('start dublin', 'start'), ('start mountain', 'start'),
        ('next oncology', 'nextoncology'), ('next virginia', 'nextoncology'), ('next ', 'nextoncology'),
        ('us oncology research', 'usoncology'),
        ('tennessee oncology', 'tennesseeoncology'), ('texas oncology', 'texasoncology'),
        ('florida cancer specialist', 'floridacancer'), ('florida cancer', 'floridacancer'),
        ('highlands oncology', 'highlands'),
        # ACADEMIC MEDICAL CENTERS
        ('smilow', 'yale'), ('yale new haven', 'yale'), ('yale cancer', 'yale'),
        ('nyu langone', 'nyulangone'), ('new york university', 'nyulangone'),
        ('columbia university', 'columbia'), ('weill cornell', 'weillcornell'),
        ('emory winship', 'emory'), ('winship cancer', 'emory'), ('emory university', 'emory'),
        ('washington university', 'washu'), ('siteman cancer', 'siteman'),
        ('barnes-jewish', 'barnesjewish'),
        ('university of rochester', 'urochester'), ('wilmot cancer', 'urochester'),
        ('university of kansas', 'ukansas'), ('university of wisconsin', 'uwisconsin'),
        ('university of iowa', 'uiowa'), ('university of michigan', 'umichigan'),
        ('hillman cancer', 'upitt'), ('university of pittsburgh', 'upitt'),
        ('university of colorado', 'ucolorado'), ('university of cincinnati', 'ucincinnati'),
        ('university of miami', 'umiami'), ('oregon health', 'ohsu'),
        ('stanford', 'stanford'), ('vanderbilt', 'vanderbilt'), ('duke', 'duke'),
        ('massachusetts general', 'mgh'), ('mass general', 'mgh'),
        ('beth israel', 'bidmc'), ('brigham', 'brigham'),
        ('hospital of the university of pennsylvania', 'upenn'),
        ('university of pennsylvania', 'upenn'),
        ('university of florida', 'uflorida'),
        ('university of southern california', 'usc'),
        ('university of texas southwestern', 'utsw'), ('ut southwestern', 'utsw'),
        # UC SYSTEM
        ('uc san diego', 'ucsd'), ('university of california san diego', 'ucsd'),
        ('moores cancer center', 'ucsd'),
        ('uc irvine', 'ucirvine'), ('chao family', 'ucirvine'),
        ('university of california, irvine', 'ucirvine'), ('university of california irvine', 'ucirvine'),
        ('ucla', 'ucla'), ('university of california, los angeles', 'ucla'),
        ('uc davis', 'ucdavis'), ('university of california, davis', 'ucdavis'),
        ('ucsf', 'ucsf'), ('university of california, san francisco', 'ucsf'),
        ('university of california san francisco', 'ucsf'),
        # BAYLOR
        ('baylor scott', 'baylorscott'), ('baylor college of medicine', 'bcm'),
        # OTHER US
        ('atlantic health', 'atlantichealth'), ('northwell health', 'northwell'),
        ('ochsner health', 'ochsner'), ('medical college of wisconsin', 'mcw'),
        ('hoag memorial', 'hoag'), ('mount sinai', 'mountsinai'), ('icahn school', 'mountsinai'),
        ('hackensack', 'hackensack'), ('lehigh valley', 'lehighvalley'),
        ('mary crowley', 'marycrowley'), ('honorhealth', 'honorhealth'),
        ('northwestern', 'northwestern'), ('rush university', 'rush'),
        ('university of chicago', 'uchicago'),
        ('indiana university', 'iuhealth'),
        # CANADIAN
        ('princess margaret', 'princessmargaret'), ('ottawa hospital', 'ottawahospital'),
        ('mcgill', 'mcgill'), ('sunnybrook', 'sunnybrook'),
        # AUSTRALIAN
        ('peter maccallum', 'petermac'), ('chris obrien lifehouse', 'lifehouse'),
        ('alfred hospital', 'alfred'), ('kinghorn cancer', 'kinghorn'),
        ('st vincent', 'stvincent'), ('monash', 'monash'),
        # EUROPEAN
        ('gustave roussy', 'gustaveroussy'), ('centre leon berard', 'leonberard'),
        ('charite', 'charite'), ('vall d hebron', 'vallhebron'), ("vall d'hebron", 'vallhebron'),
        ('hospital universitario 12 de octubre', '12octubre'),
        ('institut curie', 'curie'),
        # ASIAN
        ('national cancer center hospital east', 'nccheast'),
        ('national cancer center hospital', 'ncch'),
        ('cancer institute hospital', 'jfcr'),
        ('aichi cancer center', 'aichi'), ('kanagawa cancer', 'kanagawa'),
        ('shizuoka cancer', 'shizuoka'),
        ('fudan university', 'fudan'), ('beijing cancer', 'beijingcancer'),
        ('harbin medical', 'harbin'),
        ('seoul national university', 'snuh'), ('asan medical center', 'asan'),
        ('severance hospital', 'severance'),
        ('national cancer centre singapore', 'nccs'),
        ('national taiwan university', 'ntuh'),
    ]
    
    keywords = set()
    
    exact_matches = {'start': 'start', 'next': 'nextoncology', 'scri': 'sarahcannon'}
    if n in exact_matches:
        keywords.add(exact_matches[n])
        return keywords
    
    for phrase, keyword in key_identifiers:
        if phrase in n:
            keywords.add(keyword)
            break  # First match wins
    
    return keywords


def are_institutions_similar(name1: str, name2: str) -> bool:
    """Determine if two institution names represent the same institution."""
    n1 = name1.lower().strip()
    n2 = name2.lower().strip()
    
    if n1 == n2:
        return True
    
    generic_names = ['research site', 'local institution', 'site ', 'location ']
    if any(gen in n1 for gen in generic_names) or any(gen in n2 for gen in generic_names):
        return n1 == n2
    
    keywords1 = extract_institution_keywords(name1)
    keywords2 = extract_institution_keywords(name2)
    
    if keywords1 and keywords2:
        return keywords1 == keywords2
    
    basic_ratio = similarity_ratio(n1, n2)
    if basic_ratio >= 0.85:
        return True
    
    if (n1 in n2 or n2 in n1) and basic_ratio >= 0.75:
        return True
    
    return False


def get_clean_institution_name(df: pd.DataFrame) -> pd.Series:
    """Create a cleaned institution name column that merges similar institutions."""
    institution_clean = df['Institution'].copy()
    
    PREFERRED_CANONICAL = {
        'mayo': 'Mayo Clinic',
        'mdanderson': 'MD Anderson Cancer Center',
        'msk': 'Memorial Sloan Kettering Cancer Center',
        'danafarber': 'Dana-Farber Cancer Institute',
        'hopkins': 'Johns Hopkins Sidney Kimmel Cancer Center',
        'cedarssinai': 'Cedars-Sinai Medical Center',
        'moffitt': 'Moffitt Cancer Center',
        'cityofhope': 'City of Hope',
        'clevelandclinic': 'Cleveland Clinic',
        'huntsman': 'Huntsman Cancer Institute',
        'fredhutch': 'Fred Hutchinson Cancer Center',
        'roswellpark': 'Roswell Park Comprehensive Cancer Center',
        'banner': 'Banner MD Anderson Cancer Center',
        'sarahcannon': 'Sarah Cannon Research Institute',
        'start': 'START (South Texas Accelerated Research Therapeutics)',
        'nextoncology': 'NEXT Oncology',
        'usoncology': 'US Oncology Research',
        'tennesseeoncology': 'Tennessee Oncology',
        'texasoncology': 'Texas Oncology',
        'floridacancer': 'Florida Cancer Specialists',
        'highlands': 'Highlands Oncology Group',
        'yale': 'Yale Cancer Center',
        'nyulangone': 'NYU Langone Health',
        'columbia': 'Columbia University Irving Medical Center',
        'weillcornell': 'Weill Cornell Medicine',
        'emory': 'Emory Winship Cancer Institute',
        'washu': 'Washington University in St. Louis',
        'siteman': 'Siteman Cancer Center',
        'barnesjewish': 'Barnes-Jewish Hospital',
        'urochester': 'University of Rochester Wilmot Cancer Institute',
        'ukansas': 'University of Kansas Cancer Center',
        'uwisconsin': 'University of Wisconsin Carbone Cancer Center',
        'uiowa': 'University of Iowa Holden Comprehensive Cancer Center',
        'umichigan': 'University of Michigan Rogel Cancer Center',
        'upitt': 'UPMC Hillman Cancer Center',
        'ucolorado': 'University of Colorado Cancer Center',
        'ucincinnati': 'University of Cincinnati Cancer Center',
        'umiami': 'Sylvester Comprehensive Cancer Center',
        'ohsu': 'OHSU Knight Cancer Institute',
        'stanford': 'Stanford Cancer Institute',
        'vanderbilt': 'Vanderbilt-Ingram Cancer Center',
        'duke': 'Duke Cancer Institute',
        'mgh': 'Massachusetts General Hospital',
        'bidmc': 'Beth Israel Deaconess Medical Center',
        'brigham': "Brigham and Women's Hospital",
        'upenn': 'Penn Medicine Abramson Cancer Center',
        'uflorida': 'UF Health Cancer Center',
        'usc': 'USC Norris Comprehensive Cancer Center',
        'utsw': 'UT Southwestern Simmons Comprehensive Cancer Center',
        'ucsd': 'UC San Diego Moores Cancer Center',
        'ucirvine': 'UC Irvine Chao Family Comprehensive Cancer Center',
        'ucla': 'UCLA Jonsson Comprehensive Cancer Center',
        'ucdavis': 'UC Davis Comprehensive Cancer Center',
        'ucsf': 'UCSF Helen Diller Family Comprehensive Cancer Center',
        'baylorscott': 'Baylor Scott & White',
        'bcm': 'Baylor College of Medicine',
        'atlantichealth': 'Atlantic Health System',
        'northwell': 'Northwell Health',
        'ochsner': 'Ochsner Cancer Institute',
        'mcw': 'Medical College of Wisconsin',
        'hoag': 'Hoag Family Cancer Institute',
        'mountsinai': 'Mount Sinai Health System',
        'hackensack': 'Hackensack University Medical Center',
        'lehighvalley': 'Lehigh Valley Health Network',
        'marycrowley': 'Mary Crowley Cancer Research',
        'honorhealth': 'HonorHealth Research Institute',
        'northwestern': 'Northwestern Medicine',
        'rush': 'Rush University Medical Center',
        'uchicago': 'University of Chicago Medicine',
        'iuhealth': 'Indiana University Health',
        'princessmargaret': 'Princess Margaret Cancer Centre',
        'ottawahospital': 'The Ottawa Hospital Cancer Centre',
        'mcgill': 'McGill University Health Centre',
        'sunnybrook': 'Sunnybrook Health Sciences Centre',
        'petermac': 'Peter MacCallum Cancer Centre',
        'lifehouse': "Chris O'Brien Lifehouse",
        'alfred': 'The Alfred Hospital',
        'kinghorn': 'Kinghorn Cancer Centre',
        'stvincent': "St Vincent's Hospital",
        'monash': 'Monash Health',
        'gustaveroussy': 'Gustave Roussy',
        'leonberard': 'Centre Léon Bérard',
        'charite': 'Charité - Universitätsmedizin Berlin',
        'vallhebron': "Vall d'Hebron Institute of Oncology",
        '12octubre': 'Hospital Universitario 12 de Octubre',
        'curie': 'Institut Curie',
        'nccheast': 'National Cancer Center Hospital East',
        'ncch': 'National Cancer Center Hospital',
        'jfcr': 'Cancer Institute Hospital of JFCR',
        'aichi': 'Aichi Cancer Center',
        'kanagawa': 'Kanagawa Cancer Center',
        'shizuoka': 'Shizuoka Cancer Center',
        'fudan': 'Fudan University Shanghai Cancer Center',
        'beijingcancer': 'Beijing Cancer Hospital',
        'harbin': 'Harbin Medical University Cancer Hospital',
        'asan': 'Asan Medical Center',
        'snuh': 'Seoul National University Hospital',
        'severance': 'Severance Hospital',
        'nccs': 'National Cancer Centre Singapore',
        'ntuh': 'National Taiwan University Hospital',
    }
    
    idx_to_canonical = {}
    
    for idx, row in df.iterrows():
        inst = row['Institution']
        norm = normalize_institution_name(inst)
        keywords = extract_institution_keywords(norm)
        
        if keywords:
            keyword = list(keywords)[0]
            if keyword in PREFERRED_CANONICAL:
                idx_to_canonical[idx] = PREFERRED_CANONICAL[keyword]
            else:
                idx_to_canonical[idx] = norm
        else:
            idx_to_canonical[idx] = norm
    
    # Second pass: for institutions without keywords, check similarity within same location
    df['_location_key'] = (
        df['City'].fillna('').astype(str) + '|||' + 
        df['State'].fillna('').astype(str) + '|||' + 
        df['Country'].fillna('').astype(str)
    )
    
    location_groups = df.groupby('_location_key')
    
    for location_key, group in location_groups:
        if len(group) <= 1:
            continue
        
        indices = group.index.tolist()
        institutions = group['Institution'].tolist()
        
        for i, idx1 in enumerate(indices):
            inst1 = institutions[i]
            norm1 = normalize_institution_name(inst1)
            keywords1 = extract_institution_keywords(norm1)
            
            if keywords1:
                continue
            
            if any(gen in norm1.lower() for gen in ['research site', 'local institution', 'site ', 'location ', 'clinical trial site']):
                continue
            
            for j, idx2 in enumerate(indices[i+1:], start=i+1):
                inst2 = institutions[j]
                norm2 = normalize_institution_name(inst2)
                keywords2 = extract_institution_keywords(norm2)
                
                if keywords2:
                    continue
                
                if are_institutions_similar(norm1, norm2):
                    if idx1 in idx_to_canonical:
                        idx_to_canonical[idx2] = idx_to_canonical[idx1]
                    else:
                        idx_to_canonical[idx1] = norm1
                        idx_to_canonical[idx2] = norm1
    
    for idx in df.index:
        if idx in idx_to_canonical:
            institution_clean.loc[idx] = idx_to_canonical[idx]
        else:
            institution_clean.loc[idx] = normalize_institution_name(df.loc[idx, 'Institution'])
    
    return institution_clean


# ==============================================================================
# CORE SCRAPING LOGIC
# ==============================================================================
SCRIPT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = SCRIPT_DIR / "output"


def fetch_trial_data(nct_id: str) -> Optional[Dict]:
    """Fetch full trial data from API."""
    url = f"{BASE_URL}/{nct_id}"
    try:
        response = requests.get(url, params={"format": "json"}, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"    Error fetching {nct_id}: {e}")
        return None


def extract_locations(study_data: Dict) -> List[Dict]:
    """Extract location data from API response."""
    protocol = study_data.get("protocolSection", {})
    
    # Get trial info
    id_module = protocol.get("identificationModule", {})
    nct_id = id_module.get("nctId", "")
    trial_name = id_module.get("briefTitle", "")
    
    # Get sponsor info
    sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
    lead_sponsor = sponsor_module.get("leadSponsor", {})
    sponsor_name = lead_sponsor.get("name", "")
    
    # Get central contacts
    contacts_module = protocol.get("contactsLocationsModule", {})
    central_contacts = contacts_module.get("centralContacts", [])
    
    study_contact_name = ""
    study_contact_phone = ""
    study_contact_email = ""
    study_contact_backup_name = ""
    study_contact_backup_phone = ""
    study_contact_backup_email = ""
    
    if len(central_contacts) > 0:
        c = central_contacts[0]
        study_contact_name = c.get("name", "")
        study_contact_phone = c.get("phone", "")
        study_contact_email = c.get("email", "")
    
    if len(central_contacts) > 1:
        c = central_contacts[1]
        study_contact_backup_name = c.get("name", "")
        study_contact_backup_phone = c.get("phone", "")
        study_contact_backup_email = c.get("email", "")
    
    # Get locations
    locations = contacts_module.get("locations", [])
    
    results = []
    for loc in locations:
        facility = loc.get("facility", "")
        city = loc.get("city", "")
        state = loc.get("state", "")
        zip_code = loc.get("zip", "")
        country = loc.get("country", "")
        
        # Get contacts for this location
        loc_contacts = loc.get("contacts", [])
        
        contact_name = ""
        contact_phone = ""
        contact_email = ""
        contact_2_name = ""
        contact_2_phone = ""
        contact_2_email = ""
        contact_3 = ""
        
        if len(loc_contacts) > 0:
            c = loc_contacts[0]
            contact_name = c.get("name", "")
            contact_phone = c.get("phone", "")
            contact_email = c.get("email", "")
        
        if len(loc_contacts) > 1:
            c = loc_contacts[1]
            contact_2_name = c.get("name", "")
            contact_2_phone = c.get("phone", "")
            contact_2_email = c.get("email", "")
        
        if len(loc_contacts) > 2:
            c = loc_contacts[2]
            contact_3 = f"{c.get('name', '')} {c.get('phone', '')} {c.get('email', '')}".strip()
        
        results.append({
            "NCT Code": nct_id,
            "Trial Name": trial_name,
            "Trial URL": f"https://clinicaltrials.gov/study/{nct_id}",
            "Institution": facility,
            "City": city,
            "State": state,
            "Zip": zip_code,
            "Country": country,
            "Contact Name": contact_name,
            "Contact Phone": contact_phone,
            "Contact Email": contact_email,
            "Contact 2 Name": contact_2_name,
            "Contact 2 Phone": contact_2_phone,
            "Contact 2 Email": contact_2_email,
            "Contact 3": contact_3,
            "Study Contact Name": study_contact_name,
            "Study Contact Phone": study_contact_phone,
            "Study Contact Email": study_contact_email,
            "Study Contact Backup Name": study_contact_backup_name,
            "Study Contact Backup Phone": study_contact_backup_phone,
            "Study Contact Backup Email": study_contact_backup_email,
            "Sponsor": sponsor_name,
        })
    
    return results


def load_net_new_trials():
    """Load the net new trials from the Google Sheet."""
    sheet_id = '1zvh9MQBJd137oHUk3f-MlMP7eXd6r48P6gBKemx_93I'
    gid = '667658959'
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}'
    
    df = pd.read_csv(url, header=1)
    
    # Get the net new trials section (the .1 columns)
    net_new = df[['NCT Code.1', 'Trial Name.1', 'Trial URL.1', 'Priority.1', 'Status.1', 
                  'Mutation Type.1', 'Cancer Type.1']].copy()
    net_new = net_new.dropna(subset=['NCT Code.1'])
    
    # Rename columns
    net_new.columns = ['NCT Code', 'Trial Name', 'Trial URL', 'Priority', 'Status', 
                       'Mutation Type', 'Cancer Type']
    
    return net_new


def main():
    print("=" * 70)
    print("  SCRAPING LOCATIONS FOR 12/16/2024 NET NEW TRIALS")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Load trials to scrape
    print("\n  Loading net new trials from Google Sheet...")
    trials_df = load_net_new_trials()
    print(f"  Found {len(trials_df)} trials to scrape")
    
    # Get unique NCT codes
    nct_codes = trials_df['NCT Code'].unique()
    print(f"  Unique NCT codes: {len(nct_codes)}")
    
    # Create a lookup for trial metadata
    trial_meta = {}
    for _, row in trials_df.iterrows():
        nct = row['NCT Code']
        if nct not in trial_meta:
            trial_meta[nct] = {
                'Priority': row['Priority'],
                'Mutation Type': row['Mutation Type'],
                'Cancer Type': row['Cancer Type'],
            }
    
    # Scrape locations for each trial
    print("\n  Scraping locations...")
    all_locations = []
    errors = []
    
    for i, nct_id in enumerate(nct_codes, 1):
        if i % 50 == 0 or i == 1 or i <= 5:
            print(f"    [{i}/{len(nct_codes)}] Processing {nct_id}... (locations so far: {len(all_locations)})")
        
        study_data = fetch_trial_data(nct_id)
        if not study_data:
            errors.append(nct_id)
            continue
        
        locations = extract_locations(study_data)
        
        # Add metadata from sheet
        meta = trial_meta.get(nct_id, {})
        for loc in locations:
            loc['Priority'] = meta.get('Priority', '')
            loc['Mutation Type'] = meta.get('Mutation Type', '')
            loc['Cancer Type'] = meta.get('Cancer Type', '')
        
        all_locations.extend(locations)
        time.sleep(0.15)
    
    # Create DataFrame
    df = pd.DataFrame(all_locations)
    
    # Add Institution_clean column using fuzzy matching
    print("\n  Normalizing institution names...")
    df['Institution_clean'] = get_clean_institution_name(df)
    
    # Drop the temporary _location_key column if it exists
    if '_location_key' in df.columns:
        df = df.drop(columns=['_location_key'])
    
    # Count unique institutions
    raw_institutions = df['Institution'].nunique()
    clean_institutions = df['Institution_clean'].nunique()
    print(f"    Raw institutions: {raw_institutions}")
    print(f"    Normalized institutions: {clean_institutions}")
    print(f"    Merged: {raw_institutions - clean_institutions} duplicates")
    
    # Reorder columns (Institution_clean right after Institution)
    column_order = [
        'NCT Code', 'Trial Name', 'Trial URL', 'Priority', 'Mutation Type', 'Cancer Type',
        'Institution', 'Institution_clean', 'City', 'State', 'Zip', 'Country',
        'Contact Name', 'Contact Phone', 'Contact Email',
        'Contact 2 Name', 'Contact 2 Phone', 'Contact 2 Email', 'Contact 3',
        'Study Contact Name', 'Study Contact Phone', 'Study Contact Email',
        'Study Contact Backup Name', 'Study Contact Backup Phone', 'Study Contact Backup Email',
        'Sponsor'
    ]
    df = df[column_order]
    
    # Save to CSV
    output_file = OUTPUT_DIR / "net_new_trials_1216_center_level.csv"
    df.to_csv(output_file, index=False)
    
    # Summary
    print("\n" + "=" * 70)
    print("  COMPLETE!")
    print("=" * 70)
    print(f"\n  Trials processed: {len(nct_codes)}")
    print(f"  Errors: {len(errors)}")
    print(f"  Total locations scraped: {len(df)}")
    print()
    print(f"  By Priority:")
    for p in sorted(df['Priority'].dropna().unique()):
        count = len(df[df['Priority'] == p])
        print(f"    {p}: {count} locations")
    print()
    print(f"  By Country (top 10):")
    for country, count in df['Country'].value_counts().head(10).items():
        print(f"    {country}: {count}")
    print()
    print(f"  By Institution_clean (top 15):")
    for inst, count in df['Institution_clean'].value_counts().head(15).items():
        print(f"    {inst}: {count}")
    print()
    print(f"  Saved to: {output_file}")
    
    if errors:
        print(f"\n  Errors (could not fetch):")
        for e in errors[:10]:
            print(f"    {e}")
        if len(errors) > 10:
            print(f"    ... and {len(errors) - 10} more")
    
    return df


if __name__ == "__main__":
    df = main()

