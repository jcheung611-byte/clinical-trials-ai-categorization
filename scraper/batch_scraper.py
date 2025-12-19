import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
from typing import List, Dict
import re
from difflib import SequenceMatcher
from scraper import scrape_clinicaltrials_locations


def extract_nct_from_url(url: str) -> str:
    """Extract NCT ID from a ClinicalTrials.gov URL."""
    match = re.search(r'NCT\d+', url)
    if match:
        return match.group(0)
    return None


def normalize_institution_name(name: str) -> str:
    """
    Normalize institution name by removing site numbers, extra spaces, and standardizing punctuation.
    
    Args:
        name: Original institution name
    
    Returns:
        Normalized institution name for comparison
    """
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
    
    # Strip leading/trailing whitespace
    normalized = normalized.strip()
    
    return normalized


def similarity_ratio(str1: str, str2: str) -> float:
    """
    Calculate similarity ratio between two strings.
    
    Args:
        str1, str2: Strings to compare
    
    Returns:
        Similarity ratio between 0 and 1
    """
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def extract_institution_keywords(name: str) -> set:
    """
    Extract distinctive keywords from an institution name.
    Returns key identifying terms that distinguish this institution.
    
    Args:
        name: Institution name
    
    Returns:
        Set of key identifying terms
    """
    n = name.lower().strip()
    
    # List of known distinctive institution identifiers
    # These are multi-word phrases or unique institution names
    # IMPORTANT: More specific phrases must come BEFORE more general ones
    # Use tuples with first match wins to avoid multiple keywords for same institution
    key_identifiers = [
        # =====================================================================
        # MAJOR CANCER CENTERS
        # =====================================================================
        # Banner MD Anderson (Gilbert, AZ) - must be before 'md anderson'
        ('banner md anderson', 'banner'),
        ('banner health', 'banner'),
        # MD Anderson (Houston, TX)
        ('md anderson', 'mdanderson'),
        ('m.d. anderson', 'mdanderson'),
        # Memorial Sloan Kettering (NYC)
        ('memorial sloan kettering', 'msk'),
        ('memorial sloan-kettering', 'msk'),
        ('sloan kettering', 'msk'),
        ('sloan-kettering', 'msk'),
        # Dana-Farber (Boston)
        ('dana farber', 'danafarber'),
        ('dana-farber', 'danafarber'),
        # Mayo Clinic (all locations - Phoenix, Jacksonville, Rochester)
        ('mayo clinic', 'mayo'),
        # Johns Hopkins / Sidney Kimmel (Baltimore)
        ('sidney kimmel', 'hopkins'),
        ('johns hopkins', 'hopkins'),
        ('john hopkins', 'hopkins'),
        # Cedars-Sinai (Los Angeles)
        ('cedars-sinai', 'cedarssinai'),
        ('cedars sinai', 'cedarssinai'),
        ('cedars-sanai', 'cedarssinai'),
        # Moffitt (Tampa)
        ('moffitt', 'moffitt'),
        # City of Hope (Duarte, CA)
        ('city of hope', 'cityofhope'),
        # Cleveland Clinic (Cleveland)
        ('cleveland clinic', 'clevelandclinic'),
        # Huntsman (Salt Lake City)
        ('huntsman', 'huntsman'),
        # Fred Hutchinson (Seattle)
        ('fred hutchinson', 'fredhutch'),
        # Roswell Park (Buffalo)
        ('roswell park', 'roswellpark'),
        
        # =====================================================================
        # RESEARCH NETWORKS
        # =====================================================================
        # Sarah Cannon Research Institute / SCRI (Nashville + affiliates)
        ('sarah cannon', 'sarahcannon'),
        ('scri oncology', 'sarahcannon'),
        ('scri-', 'sarahcannon'),
        ('scri ', 'sarahcannon'),
        # START = South Texas Accelerated Research Therapeutics (all locations)
        ('south texas accelerated', 'start'),
        ('start san antonio', 'start'),
        ('start midwest', 'start'),
        ('start dublin', 'start'),
        ('start mountain', 'start'),
        # NEXT Oncology (all locations)
        ('next oncology', 'nextoncology'),
        ('next virginia', 'nextoncology'),
        ('next ', 'nextoncology'),  # Catch "NEXT Dallas", "NEXT " etc.
        # US Oncology Research Network
        ('us oncology research', 'usoncology'),
        # Tennessee Oncology (all locations)
        ('tennessee oncology', 'tennesseeoncology'),
        # Texas Oncology (all locations)
        ('texas oncology', 'texasoncology'),
        # Florida Cancer Specialists (all locations)
        ('florida cancer specialist', 'floridacancer'),
        ('florida cancer', 'floridacancer'),
        # Highlands Oncology (Arkansas)
        ('highlands oncology', 'highlands'),
        # Nebraska Cancer Specialists
        ('nebraska cancer specialist', 'nebraskacancer'),
        # Virginia Cancer Specialists
        ('virginia cancer specialist', 'virginiacancer'),
        
        # =====================================================================
        # ACADEMIC MEDICAL CENTERS
        # =====================================================================
        # Yale/Smilow (New Haven)
        ('smilow', 'yale'),
        ('yale new haven', 'yale'),
        ('yale cancer', 'yale'),
        # NYU Langone (NYC)
        ('nyu langone', 'nyulangone'),
        ('new york university', 'nyulangone'),
        # Columbia (NYC)
        ('columbia university', 'columbia'),
        # Weill Cornell (NYC)
        ('weill cornell', 'weillcornell'),
        # NY Presbyterian (NYC)
        ('new york presbyterian', 'nypresbyterian'),
        # Emory / Winship (Atlanta)
        ('emory winship', 'emory'),
        ('winship cancer', 'emory'),
        ('emory university', 'emory'),
        # Georgetown (DC)
        ('georgetown university', 'georgetown'),
        # Washington University (St. Louis)
        ('washington university', 'washu'),
        # Siteman Cancer Center (St. Louis - affiliated with Wash U)
        ('siteman cancer', 'siteman'),
        # Barnes-Jewish (St. Louis - affiliated with Wash U)
        ('barnes-jewish', 'barnesjewish'),
        # University of Rochester / Wilmot (Rochester, NY)
        ('university of rochester', 'urochester'),
        ('wilmot cancer', 'urochester'),
        # University of Kansas (Kansas City)
        ('university of kansas', 'ukansas'),
        # University of Wisconsin (Madison)
        ('university of wisconsin', 'uwisconsin'),
        # University of Iowa
        ('university of iowa', 'uiowa'),
        # University of Michigan (Ann Arbor)
        ('university of michigan', 'umichigan'),
        # University of Pittsburgh / Hillman (Pittsburgh)
        ('hillman cancer', 'upitt'),
        ('university of pittsburgh', 'upitt'),
        # University of Colorado (Aurora)
        ('university of colorado', 'ucolorado'),
        # University of Cincinnati
        ('university of cincinnati', 'ucincinnati'),
        # University of Miami
        ('university of miami', 'umiami'),
        # Oregon Health and Science University
        ('oregon health', 'ohsu'),
        # Stanford
        ('stanford', 'stanford'),
        # Vanderbilt (Nashville)
        ('vanderbilt', 'vanderbilt'),
        # Duke (Durham)
        ('duke', 'duke'),
        # Mass General (Boston)
        ('massachusetts general', 'mgh'),
        ('mass general', 'mgh'),
        # Beth Israel (Boston)
        ('beth israel', 'bidmc'),
        # Brigham (Boston)
        ('brigham', 'brigham'),
        # Penn / Hospital of Univ of Pennsylvania (Philadelphia)
        ('hospital of the university of pennsylvania', 'upenn'),
        ('university of pennsylvania', 'upenn'),
        # Jefferson (Philadelphia)
        ('jefferson university', 'jefferson'),
        # University of Florida
        ('university of florida', 'uflorida'),
        # University of Southern California
        ('university of southern california', 'usc'),
        # University of Texas Southwestern (Dallas)
        ('university of texas southwestern', 'utsw'),
        ('ut southwestern', 'utsw'),
        
        # =====================================================================
        # UC SYSTEM (California)
        # =====================================================================
        ('uc san diego', 'ucsd'),
        ('university of california san diego', 'ucsd'),
        ('moores cancer center', 'ucsd'),
        ('uc irvine', 'ucirvine'),
        ('chao family', 'ucirvine'),
        ('university of california, irvine', 'ucirvine'),
        ('university of california irvine', 'ucirvine'),
        ('ucla', 'ucla'),
        ('university of california, los angeles', 'ucla'),
        ('university of california los angeles', 'ucla'),
        ('uc davis', 'ucdavis'),
        ('university of california, davis', 'ucdavis'),
        ('ucsf', 'ucsf'),
        ('university of california, san francisco', 'ucsf'),
        ('university of california san francisco', 'ucsf'),
        ('university of california at san francisco', 'ucsf'),
        
        # =====================================================================
        # BAYLOR SYSTEM (Texas) - keep separate
        # =====================================================================
        ('baylor scott', 'baylorscott'),
        ('baylor college of medicine', 'bcm'),
        
        # =====================================================================
        # OTHER US INSTITUTIONS
        # =====================================================================
        ('atlantic health', 'atlantichealth'),
        ('northwell health', 'northwell'),
        ('ochsner health', 'ochsner'),
        ('medical college of wisconsin', 'mcw'),
        ('hoag memorial', 'hoag'),
        ('christ hospital', 'christhospital'),
        ('stephenson cancer', 'stephenson'),
        ('icahn school', 'mountsinai'),
        ('mount sinai', 'mountsinai'),
        ('hackensack', 'hackensack'),
        ('lehigh valley', 'lehighvalley'),
        ('mary crowley', 'marycrowley'),
        ('swedish', 'swedish'),
        ('virginia mason', 'virginiamason'),
        ('case western', 'casewestern'),
        ('honorhealth', 'honorhealth'),
        ('ironwood cancer', 'ironwood'),
        ('community health network', 'communityhealth'),
        ('miriam hospital', 'miriam'),
        ('rhode island hospital', 'rihospital'),
        ('west chester hospital', 'westchester'),
        
        # =====================================================================
        # CANADIAN INSTITUTIONS
        # =====================================================================
        ('princess margaret', 'princessmargaret'),
        ('ottawa hospital', 'ottawahospital'),
        
        # =====================================================================
        # AUSTRALIAN INSTITUTIONS
        # =====================================================================
        ('peter maccallum', 'petermac'),
        ('chris obrien lifehouse', 'lifehouse'),
        ('alfred hospital', 'alfred'),
        ('kinghorn cancer', 'kinghorn'),
        ('st vincent', 'stvincent'),
        ('monash', 'monash'),
        
        # =====================================================================
        # EUROPEAN INSTITUTIONS
        # =====================================================================
        ('gustave roussy', 'gustaveroussy'),
        ('centre leon berard', 'leonberard'),
        ('claudius regaud', 'claudiusregaud'),
        ('oncopole', 'claudiusregaud'),
        ('charite', 'charite'),
        ('vall d hebron', 'vallhebron'),
        ('vall d\'hebron', 'vallhebron'),
        ('hospital universitario 12 de octubre', '12octubre'),
        ('fundacion jimenez diaz', 'jimenezdiaz'),
        
        # =====================================================================
        # ASIAN INSTITUTIONS
        # =====================================================================
        # Japan
        ('national cancer center hospital east', 'nccheast'),
        ('national cancer center hospital', 'ncch'),
        ('cancer institute hospital', 'jfcr'),
        ('aichi cancer center', 'aichi'),
        ('kanagawa cancer', 'kanagawa'),
        ('shizuoka cancer', 'shizuoka'),
        ('shikoku cancer', 'shikoku'),
        ('osaka international', 'osakainternational'),
        ('kansai medical', 'kansai'),
        ('kindai university', 'kindai'),
        ('hokkaido university', 'hokkaido'),
        ('tohoku university', 'tohoku'),
        ('yamaguchi university', 'yamaguchi'),
        # China
        ('fudan university', 'fudan'),
        ('beijing cancer', 'beijingcancer'),
        ('harbin medical', 'harbin'),
        ('chinese academy of medical sciences', 'cams'),
        ('shanghai zhongshan', 'shanghaizhongshan'),
        ('zhongshan hospital', 'shanghaizhongshan'),
        ('shanghai chest', 'shanghaichest'),
        ('shanghai pudong', 'shanghaipudong'),
        ('shanghai east', 'shanghaieast'),
        ('yunnan cancer', 'yunnancancer'),
        ('jiangxi cancer', 'jiangxicancer'),
        ('guangdong pharmaceutical', 'guangdongpharma'),
        ('chinese pla general', 'plageneralhospital'),
        # Korea - must be before Singapore to avoid "national university" conflicts
        ('seoul national university', 'snuh'),
        ('asan medical center', 'asan'),
        ('severance hospital', 'severance'),
        # Singapore
        ('national cancer centre singapore', 'nccs'),
        ('national university hospital', 'nuh'),
        ('tan tock seng', 'ttsh'),
        # Taiwan
        ('national taiwan university', 'ntuh'),
        ('national cheng kung', 'ncku'),
        ('taipei veterans', 'taipeivet'),
        # Hong Kong
        ('queen mary hospital', 'queenmary'),
        ('prince of wales', 'princeofwales'),
        # New Zealand
        ('auckland city hospital', 'auckland'),
    ]
    
    keywords = set()
    
    # Handle exact matches for short network names first
    exact_matches = {
        'start': 'start',
        'next': 'nextoncology',
        'scri': 'sarahcannon',
    }
    if n in exact_matches:
        keywords.add(exact_matches[n])
        return keywords
    
    # Only take the FIRST matching keyword to avoid multiple keywords per institution
    for phrase, keyword in key_identifiers:
        if phrase in n:
            keywords.add(keyword)
            # Always stop after first match to avoid conflicts
            # Order of key_identifiers matters - more specific phrases should come first
            break
    
    return keywords


def are_institutions_similar(name1: str, name2: str) -> bool:
    """
    Determine if two institution names represent the same institution.
    Uses keyword matching to identify the same institution.
    
    Args:
        name1, name2: Institution names to compare
    
    Returns:
        True if institutions should be considered the same
    """
    # Normalize for comparison
    n1 = name1.lower().strip()
    n2 = name2.lower().strip()
    
    # Exact match
    if n1 == n2:
        return True
    
    # Skip generic/placeholder names
    generic_names = ['research site', 'local institution', 'site ', 'location ']
    if any(gen in n1 for gen in generic_names) or any(gen in n2 for gen in generic_names):
        # Only merge if they're exactly the same
        return n1 == n2
    
    # Extract keywords from both names
    keywords1 = extract_institution_keywords(name1)
    keywords2 = extract_institution_keywords(name2)
    
    # If both have keywords and they match, they're the same institution
    if keywords1 and keywords2:
        if keywords1 == keywords2:
            return True
        # No keyword overlap means different institutions
        return False
    
    # If one or both have no keywords, fall back to fuzzy matching
    # (for institutions not in our keyword list)
    
    # Calculate basic similarity
    basic_ratio = similarity_ratio(n1, n2)
    if basic_ratio >= 0.85:
        return True
    
    # Check if one is a substring of the other
    if (n1 in n2 or n2 in n1) and basic_ratio >= 0.75:
        return True
    
    return False


def get_clean_institution_name(df: pd.DataFrame) -> pd.Series:
    """
    Create a cleaned institution name column that merges similar institutions
    based on keyword matching GLOBALLY (regardless of location).
    
    Args:
        df: DataFrame with institution, city, state, zip, country columns
    
    Returns:
        Series with cleaned institution names
    """
    # Create a copy to work with
    institution_clean = df['Institution'].copy()
    
    # Preferred canonical names for each keyword
    # This ensures consistent, clean naming regardless of order in data
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
        # Research Networks
        'sarahcannon': 'Sarah Cannon Research Institute',
        'start': 'START (South Texas Accelerated Research Therapeutics)',
        'nextoncology': 'NEXT Oncology',
        'usoncology': 'US Oncology Research',
        'tennesseeoncology': 'Tennessee Oncology',
        'texasoncology': 'Texas Oncology',
        'floridacancer': 'Florida Cancer Specialists',
        'highlands': 'Highlands Oncology Group',
        'nebraskacancer': 'Nebraska Cancer Specialists',
        'virginiacancer': 'Virginia Cancer Specialists',
        # Academic Medical Centers
        'yale': 'Yale Cancer Center',
        'nyulangone': 'NYU Langone Health',
        'columbia': 'Columbia University Irving Medical Center',
        'weillcornell': 'Weill Cornell Medicine',
        'nypresbyterian': 'NewYork-Presbyterian Hospital',
        'emory': 'Emory Winship Cancer Institute',
        'georgetown': 'Georgetown Lombardi Comprehensive Cancer Center',
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
        'brigham': 'Brigham and Women\'s Hospital',
        'upenn': 'Penn Medicine Abramson Cancer Center',
        'jefferson': 'Sidney Kimmel Cancer Center at Jefferson',
        'uflorida': 'UF Health Cancer Center',
        'usc': 'USC Norris Comprehensive Cancer Center',
        'utsw': 'UT Southwestern Simmons Comprehensive Cancer Center',
        # UC System
        'ucsd': 'UC San Diego Moores Cancer Center',
        'ucirvine': 'UC Irvine Chao Family Comprehensive Cancer Center',
        'ucla': 'UCLA Jonsson Comprehensive Cancer Center',
        'ucdavis': 'UC Davis Comprehensive Cancer Center',
        'ucsf': 'UCSF Helen Diller Family Comprehensive Cancer Center',
        # Baylor
        'baylorscott': 'Baylor Scott & White',
        'bcm': 'Baylor College of Medicine',
        # Other US
        'atlantichealth': 'Atlantic Health System',
        'northwell': 'Northwell Health',
        'ochsner': 'Ochsner Cancer Institute',
        'mcw': 'Medical College of Wisconsin',
        'hoag': 'Hoag Family Cancer Institute',
        'christhospital': 'The Christ Hospital',
        'stephenson': 'Stephenson Cancer Center',
        'mountsinai': 'Mount Sinai Health System',
        'hackensack': 'Hackensack University Medical Center',
        'lehighvalley': 'Lehigh Valley Health Network',
        'marycrowley': 'Mary Crowley Cancer Research',
        'swedish': 'Swedish Cancer Institute',
        'virginiamason': 'Virginia Mason Medical Center',
        'casewestern': 'Case Western Reserve University',
        'honorhealth': 'HonorHealth Research Institute',
        'ironwood': 'Ironwood Cancer & Research Centers',
        'communityhealth': 'Community Health Network',
        'miriam': 'The Miriam Hospital',
        'rihospital': 'Rhode Island Hospital',
        'westchester': 'West Chester Hospital',
        # Canadian
        'princessmargaret': 'Princess Margaret Cancer Centre',
        'ottawahospital': 'The Ottawa Hospital Cancer Centre',
        # Australian
        'petermac': 'Peter MacCallum Cancer Centre',
        'lifehouse': 'Chris O\'Brien Lifehouse',
        'alfred': 'The Alfred Hospital',
        'kinghorn': 'Kinghorn Cancer Centre',
        'stvincent': 'St Vincent\'s Hospital',
        'monash': 'Monash Health',
        # European
        'gustaveroussy': 'Gustave Roussy',
        'leonberard': 'Centre Léon Bérard',
        'claudiusregaud': 'Institut Claudius Regaud',
        'charite': 'Charité - Universitätsmedizin Berlin',
        'vallhebron': 'Vall d\'Hebron Institute of Oncology',
        '12octubre': 'Hospital Universitario 12 de Octubre',
        'jimenezdiaz': 'Fundación Jiménez Díaz',
        # Japan
        'nccheast': 'National Cancer Center Hospital East',
        'ncch': 'National Cancer Center Hospital',
        'jfcr': 'Cancer Institute Hospital of JFCR',
        'aichi': 'Aichi Cancer Center',
        'kanagawa': 'Kanagawa Cancer Center',
        'shizuoka': 'Shizuoka Cancer Center',
        'shikoku': 'Shikoku Cancer Center',
        'osakainternational': 'Osaka International Cancer Institute',
        'kansai': 'Kansai Medical University Hospital',
        'kindai': 'Kindai University Hospital',
        'hokkaido': 'Hokkaido University Hospital',
        'tohoku': 'Tohoku University Hospital',
        'yamaguchi': 'Yamaguchi University Hospital',
        # China
        'fudan': 'Fudan University Shanghai Cancer Center',
        'beijingcancer': 'Beijing Cancer Hospital',
        'harbin': 'Harbin Medical University Cancer Hospital',
        'cams': 'Cancer Hospital, Chinese Academy of Medical Sciences',
        'shanghaizhongshan': 'Zhongshan Hospital, Fudan University',
        'shanghaichest': 'Shanghai Chest Hospital',
        'shanghaipudong': 'Shanghai Pudong Hospital',
        'shanghaieast': 'Shanghai East Hospital',
        'yunnancancer': 'Yunnan Cancer Hospital',
        'jiangxicancer': 'Jiangxi Cancer Hospital',
        'guangdongpharma': 'Guangdong Pharmaceutical University Hospital',
        'plageneralhospital': 'Chinese PLA General Hospital',
        # Korea/Singapore/Taiwan/HK/NZ
        'asan': 'Asan Medical Center',
        'snuh': 'Seoul National University Hospital',
        'severance': 'Severance Hospital',
        'nccs': 'National Cancer Centre Singapore',
        'nuh': 'National University Hospital Singapore',
        'ttsh': 'Tan Tock Seng Hospital',
        'ntuh': 'National Taiwan University Hospital',
        'ncku': 'National Cheng Kung University Hospital',
        'taipeivet': 'Taipei Veterans General Hospital',
        'queenmary': 'Queen Mary Hospital',
        'princeofwales': 'Prince of Wales Hospital',
        'auckland': 'Auckland City Hospital',
    }
    
    # Build a mapping of keywords to canonical names
    idx_to_canonical = {}  # index -> canonical name
    
    for idx, row in df.iterrows():
        inst = row['Institution']
        norm = normalize_institution_name(inst)
        keywords = extract_institution_keywords(norm)
        
        if keywords:
            # Use the first keyword found (should be only one due to our logic)
            keyword = list(keywords)[0]
            
            # Use preferred canonical name if available, otherwise use normalized name
            if keyword in PREFERRED_CANONICAL:
                idx_to_canonical[idx] = PREFERRED_CANONICAL[keyword]
            else:
                idx_to_canonical[idx] = norm
        else:
            # No keyword found, keep original normalized name
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
            
            # Skip if already has a keyword (handled globally above)
            if keywords1:
                continue
            
            # Skip generic names
            if any(gen in norm1.lower() for gen in ['research site', 'local institution', 'site ', 'location ', 'clinical trial site']):
                continue
            
            for j, idx2 in enumerate(indices[i+1:], start=i+1):
                inst2 = institutions[j]
                norm2 = normalize_institution_name(inst2)
                keywords2 = extract_institution_keywords(norm2)
                
                # Skip if the other has a keyword
                if keywords2:
                    continue
                
                # Check similarity for non-keyword institutions
                if are_institutions_similar(norm1, norm2):
                    # Use the first one's normalized name
                    if idx1 in idx_to_canonical:
                        idx_to_canonical[idx2] = idx_to_canonical[idx1]
                    else:
                        idx_to_canonical[idx1] = norm1
                        idx_to_canonical[idx2] = norm1
    
    # Apply the mapping
    for idx in df.index:
        if idx in idx_to_canonical:
            institution_clean.loc[idx] = idx_to_canonical[idx]
        else:
            institution_clean.loc[idx] = normalize_institution_name(df.loc[idx, 'Institution'])
    
    return institution_clean


def read_google_sheet_as_csv(sheet_url: str) -> pd.DataFrame:
    """
    Read a Google Sheet by converting the URL to CSV export format.
    
    Args:
        sheet_url: The Google Sheets sharing URL
    
    Returns:
        DataFrame with the sheet contents
    """
    # Convert the sharing URL to export URL
    # Extract the spreadsheet ID
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', sheet_url)
    if not match:
        raise ValueError("Invalid Google Sheets URL")
    
    sheet_id = match.group(1)
    
    # Create CSV export URL
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    print(f"Attempting to read Google Sheet from: {csv_url}")
    
    try:
        df = pd.read_csv(csv_url)
        print(f"Successfully loaded {len(df)} rows from Google Sheet")
        return df
    except Exception as e:
        print(f"Error reading Google Sheet: {e}")
        return None


def scrape_multiple_trials(sheet_url: str, limit: int = None) -> List[Dict[str, str]]:
    """
    Scrape multiple clinical trials from URLs in a Google Sheet.
    
    Args:
        sheet_url: URL to the Google Sheet
        limit: Optional limit on number of trials to scrape (for testing)
    
    Returns:
        List of dictionaries with all location data
    """
    # Read the Google Sheet
    df = read_google_sheet_as_csv(sheet_url)
    
    if df is None:
        print("Failed to read Google Sheet. Please check the URL and permissions.")
        return []
    
    print("\nColumns in sheet:", df.columns.tolist())
    
    # Find columns by name (case-insensitive partial match)
    study_url_col = None
    priority_col = None
    
    for col in df.columns:
        col_lower = str(col).lower()
        if 'study url' in col_lower or col_lower == 'study url':
            study_url_col = col
        elif col_lower == 'priority' or (col_lower.startswith('priority') and 'archive' not in col_lower):
            priority_col = col
    
    print(f"\nUsing '{study_url_col}' for Study URL")
    print(f"Using '{priority_col}' for Priority")
    
    if study_url_col is None:
        print("\nError: Could not find column N for Study URL")
        return []
    
    # Filter to rows with valid URLs
    df_filtered = df[df[study_url_col].notna() & (df[study_url_col] != '') & df[study_url_col].astype(str).str.contains('clinicaltrials.gov', na=False)]
    
    if limit:
        df_filtered = df_filtered.head(limit)
    
    print(f"\nFound {len(df_filtered)} trials to scrape")
    
    all_results = []
    
    for idx, row in df_filtered.iterrows():
        url = str(row[study_url_col])
        priority = str(row[priority_col]) if priority_col and pd.notna(row[priority_col]) else 'N/A'
        
        # Extract NCT ID from URL
        nct_id = extract_nct_from_url(url)
        
        if not nct_id:
            print(f"\nSkipping row {idx}: Could not extract NCT ID from {url}")
            continue
        
        print(f"\n{'='*80}")
        print(f"Scraping {nct_id} (Priority: {priority})")
        print(f"URL: {url}")
        print(f"{'='*80}")
        
        # Scrape locations for this trial (now returns trial_name, central_contacts, and locations)
        trial_name, central_contacts, locations = scrape_clinicaltrials_locations(nct_id)
        
        # Add NCT ID, trial name, URL, priority, and central contacts to each location
        for location in locations:
            location['nct_id'] = nct_id
            location['trial_name'] = trial_name
            location['study_url'] = url
            location['priority'] = priority
            # Add study-level contacts
            location['study_contact_name'] = central_contacts.get('study_contact_name', '')
            location['study_contact_phone'] = central_contacts.get('study_contact_phone', '')
            location['study_contact_email'] = central_contacts.get('study_contact_email', '')
            location['study_contact_backup_name'] = central_contacts.get('study_contact_backup_name', '')
            location['study_contact_backup_phone'] = central_contacts.get('study_contact_backup_phone', '')
            location['study_contact_backup_email'] = central_contacts.get('study_contact_backup_email', '')
        
        all_results.extend(locations)
        
        print(f"Added {len(locations)} locations from {nct_id}")
    
    return all_results


def save_combined_results(results: List[Dict[str, str]], center_output_file: str, contact_output_file: str):
    """
    Save combined results to two CSV files: center-level and contact-level.
    
    Args:
        results: List of location dictionaries
        center_output_file: Output CSV filename for center-level data
        contact_output_file: Output CSV filename for contact-level data
    """
    if not results:
        print("No results to save.")
        return
    
    df = pd.DataFrame(results)
    
    # Rename columns first for easier processing
    df.rename(columns={
        'nct_id': 'NCT Code',
        'trial_name': 'Trial Name',
        'study_url': 'Study URL',
        'priority': 'Priority',
        'institution': 'Institution',
        'city': 'City',
        'state': 'State',
        'zip': 'Zip',
        'country': 'Country',
        'contact_name': 'Contact Name',
        'contact_phone': 'Contact Phone',
        'contact_email': 'Contact Email',
        'contact_2_name': 'Contact 2 Name',
        'contact_2_phone': 'Contact 2 Phone',
        'contact_2_email': 'Contact 2 Email',
        'contact_3': 'Contact 3',
        'study_contact_name': 'Study Contact Name',
        'study_contact_phone': 'Study Contact Phone',
        'study_contact_email': 'Study Contact Email',
        'study_contact_backup_name': 'Study Contact Backup Name',
        'study_contact_backup_phone': 'Study Contact Backup Phone',
        'study_contact_backup_email': 'Study Contact Backup Email'
    }, inplace=True)
    
    # Generate cleaned institution names
    print("\nNormalizing institution names...")
    df['Institution_clean'] = get_clean_institution_name(df)
    
    # Remove the temporary location keys if they exist
    for col in ['_location_key', '_state_country_key', 'all_contacts']:
        if col in df.columns:
            df.drop(col, axis=1, inplace=True)
    
    # ========================================
    # CENTER-LEVEL OUTPUT
    # ========================================
    # Column order: NCT Code, Trial Name, Study URL, Priority, Institution, Institution_clean,
    #               City, State, Zip, Country, Contact info, Study Contact info
    center_column_order = [
        'NCT Code', 'Trial Name', 'Study URL', 'Priority',
        'Institution', 'Institution_clean', 'City', 'State', 'Zip', 'Country', 
        'Contact Name', 'Contact Phone', 'Contact Email',
        'Contact 2 Name', 'Contact 2 Phone', 'Contact 2 Email',
        'Contact 3',
        'Study Contact Name', 'Study Contact Phone', 'Study Contact Email',
        'Study Contact Backup Name', 'Study Contact Backup Phone', 'Study Contact Backup Email'
    ]
    
    # Only include columns that exist
    center_column_order = [col for col in center_column_order if col in df.columns]
    df_center = df[center_column_order].copy()
    
    df_center.to_csv(center_output_file, index=False)
    print(f"\n{'='*80}")
    print(f"✓ Saved {len(df_center)} center-level entries to {center_output_file}")
    print(f"{'='*80}")
    
    # ========================================
    # CONTACT-LEVEL OUTPUT
    # ========================================
    # Create separate rows for each contact
    contact_rows = []
    
    for _, row in df.iterrows():
        base_info = {
            'NCT Code': row['NCT Code'],
            'Trial Name': row.get('Trial Name', ''),
            'Study URL': row.get('Study URL', ''),
            'Priority': row.get('Priority', ''),
            'Institution': row['Institution'],
            'Institution_clean': row['Institution_clean'],
            'City': row['City'],
            'State': row['State'],
            'Zip': row.get('Zip', ''),
            'Country': row['Country'],
            'Study Contact Name': row.get('Study Contact Name', ''),
            'Study Contact Phone': row.get('Study Contact Phone', ''),
            'Study Contact Email': row.get('Study Contact Email', ''),
            'Study Contact Backup Name': row.get('Study Contact Backup Name', ''),
            'Study Contact Backup Phone': row.get('Study Contact Backup Phone', ''),
            'Study Contact Backup Email': row.get('Study Contact Backup Email', ''),
        }
        
        # First contact
        contact1_name = row.get('Contact Name', '')
        contact1_phone = row.get('Contact Phone', '')
        contact1_email = row.get('Contact Email', '')
        
        if contact1_name or contact1_phone or contact1_email:
            contact_row = base_info.copy()
            contact_row['Contact Name'] = contact1_name
            contact_row['Contact Phone'] = contact1_phone
            contact_row['Contact Email'] = contact1_email
            contact_rows.append(contact_row)
        else:
            # Add row even if no contact info
            contact_row = base_info.copy()
            contact_row['Contact Name'] = ''
            contact_row['Contact Phone'] = ''
            contact_row['Contact Email'] = ''
            contact_rows.append(contact_row)
        
        # Second contact (if exists)
        contact2_name = row.get('Contact 2 Name', '')
        contact2_phone = row.get('Contact 2 Phone', '')
        contact2_email = row.get('Contact 2 Email', '')
        
        if contact2_name or contact2_phone or contact2_email:
            contact_row = base_info.copy()
            contact_row['Contact Name'] = contact2_name
            contact_row['Contact Phone'] = contact2_phone
            contact_row['Contact Email'] = contact2_email
            contact_rows.append(contact_row)
        
        # Third+ contacts (if exists) - parse the condensed format
        contact3 = row.get('Contact 3', '')
        if contact3 and str(contact3).strip():
            # Format is: "Name | Phone | Email || Name2 | Phone2 | Email2"
            for contact_str in str(contact3).split('||'):
                parts = contact_str.strip().split('|')
                if len(parts) >= 3:
                    contact_row = base_info.copy()
                    contact_row['Contact Name'] = parts[0].strip()
                    contact_row['Contact Phone'] = parts[1].strip()
                    contact_row['Contact Email'] = parts[2].strip()
                    contact_rows.append(contact_row)
    
    df_contact = pd.DataFrame(contact_rows)
    
    # Column order for contact-level
    contact_column_order = [
        'NCT Code', 'Trial Name', 'Study URL', 'Priority',
        'Institution', 'Institution_clean', 'City', 'State', 'Zip', 'Country', 
        'Contact Name', 'Contact Phone', 'Contact Email',
        'Study Contact Name', 'Study Contact Phone', 'Study Contact Email',
        'Study Contact Backup Name', 'Study Contact Backup Phone', 'Study Contact Backup Email'
    ]
    contact_column_order = [col for col in contact_column_order if col in df_contact.columns]
    df_contact = df_contact[contact_column_order]
    
    df_contact.to_csv(contact_output_file, index=False)
    print(f"✓ Saved {len(df_contact)} contact-level entries to {contact_output_file}")
    print(f"{'='*80}")
    
    # Print summary
    print("\nSummary by NCT Code:")
    summary = df_center.groupby('NCT Code').size()
    for nct, count in summary.items():
        priority = df_center[df_center['NCT Code'] == nct]['Priority'].iloc[0]
        print(f"  {nct}: {count} locations (Priority: {priority})")
    
    # Print institution normalization summary
    print("\nInstitution Normalization Summary:")
    original_count = df_center['Institution'].nunique()
    clean_count = df_center['Institution_clean'].nunique()
    print(f"  Original unique institutions: {original_count}")
    print(f"  Cleaned unique institutions: {clean_count}")
    print(f"  Merged: {original_count - clean_count} duplicates")


if __name__ == "__main__":
    # Google Sheet URL
    sheet_url = "https://docs.google.com/spreadsheets/d/1zvh9MQBJd137oHUk3f-MlMP7eXd6r48P6gBKemx_93I/edit?usp=sharing"
    
    # Scrape all trials from the sheet
    print("Starting batch scraping (ALL trials from sheet)...")
    results = scrape_multiple_trials(sheet_url, limit=None)
    
    if results:
        # Save to CSV - two output files
        center_output_file = "trials_center_level.csv"
        contact_output_file = "trials_contact_level.csv"
        save_combined_results(results, center_output_file, contact_output_file)
        
        # Also save as JSON for reference
        with open("trials_data.json", 'w', encoding='utf-8') as f:
            # Remove 'all_contacts' from JSON output as it's redundant
            clean_results = []
            for r in results:
                clean_r = {k: v for k, v in r.items() if k != 'all_contacts'}
                clean_results.append(clean_r)
            json.dump(clean_results, f, indent=2, ensure_ascii=False)
        print(f"\nAlso saved JSON version to trials_data.json")
    else:
        print("\nNo results to save.")

