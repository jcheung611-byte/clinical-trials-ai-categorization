"""
Location utilities for determining SoCal proximity.
"""
import math
import pgeocode
import pandas as pd
from functools import lru_cache

# Reference location: Diamond Bar, CA (91765)
REFERENCE_ZIP = "91765"
MAX_LOCAL_DISTANCE_MILES = 150

# Initialize US zip code database
_nomi = None

def get_nomi():
    """Lazy load the nominatim database."""
    global _nomi
    if _nomi is None:
        _nomi = pgeocode.Nominatim('us')
    return _nomi


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth.
    Returns distance in miles.
    """
    R = 3959  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
         math.sin(dlon/2)**2)
    c = 2 * math.asin(math.sqrt(a))
    return R * c


@lru_cache(maxsize=10000)
def get_zip_coords(zip_code: str) -> tuple:
    """
    Get coordinates for a US zip code.
    Returns (latitude, longitude) or (None, None) if not found.
    """
    if not zip_code or pd.isna(zip_code):
        return None, None
    
    # Clean zip code (take first 5 digits)
    zip_code = str(zip_code).strip()
    if len(zip_code) > 5:
        zip_code = zip_code[:5]
    if not zip_code.isdigit() or len(zip_code) < 5:
        return None, None
    
    nomi = get_nomi()
    info = nomi.query_postal_code(zip_code)
    
    if info is not None and not math.isnan(info['latitude']):
        return info['latitude'], info['longitude']
    return None, None


def is_local_zip(zip_code: str, ref_zip: str = REFERENCE_ZIP, 
                  max_distance: float = MAX_LOCAL_DISTANCE_MILES) -> bool:
    """
    Check if a zip code is within max_distance miles of the reference zip code.
    
    Args:
        zip_code: The zip code to check
        ref_zip: Reference zip code (default: 91765, Diamond Bar, CA)
        max_distance: Maximum distance in miles to be considered local (default: 150)
    
    Returns:
        True if within max_distance miles, False otherwise
    """
    ref_lat, ref_lon = get_zip_coords(ref_zip)
    if ref_lat is None:
        return False
    
    zip_lat, zip_lon = get_zip_coords(zip_code)
    if zip_lat is None:
        return False
    
    distance = haversine_distance(ref_lat, ref_lon, zip_lat, zip_lon)
    return distance <= max_distance


def add_is_local_to_df(df: pd.DataFrame, 
                        zip_col: str = 'Zip',
                        state_col: str = 'State',
                        country_col: str = 'Country') -> pd.DataFrame:
    """
    Add 'is_local' column to a DataFrame with location data.
    
    is_local = True if:
    1. Country is United States
    2. State is California
    3. Zip code is within 150 miles of 91765 (Diamond Bar, CA)
    
    Args:
        df: DataFrame with location columns
        zip_col: Name of zip code column
        state_col: Name of state column
        country_col: Name of country column
    
    Returns:
        DataFrame with 'is_local' column added
    """
    df = df.copy()
    
    def check_is_local(row):
        # Check country
        country = str(row.get(country_col, '')).lower()
        if 'united states' not in country and 'usa' not in country:
            return False
        
        # Check state
        state = str(row.get(state_col, '')).lower()
        if 'california' not in state and state != 'ca':
            return False
        
        # Check zip distance
        zip_code = row.get(zip_col)
        return is_local_zip(zip_code)
    
    df['is_local'] = df.apply(check_is_local, axis=1)
    return df


def add_trial_has_local(center_df: pd.DataFrame, 
                         nct_col: str = 'NCT Code') -> pd.DataFrame:
    """
    Add 'has_local_center' column indicating if trial has any local centers.
    
    Args:
        center_df: DataFrame with center-level data (must have 'is_local' column)
        nct_col: Name of NCT code column
    
    Returns:
        DataFrame with 'has_local_center' aggregated per trial
    """
    if 'is_local' not in center_df.columns:
        center_df = add_is_local_to_df(center_df)
    
    # Group by trial and check if any center is local
    trial_local = center_df.groupby(nct_col)['is_local'].any().reset_index()
    trial_local.columns = [nct_col, 'has_local_center']
    
    return trial_local


if __name__ == '__main__':
    # Test the module
    print("Testing is_local calculation...")
    
    test_data = [
        ('90024', 'California', 'United States'),  # UCLA - should be local
        ('94102', 'California', 'United States'),  # SF - not local
        ('92101', 'California', 'United States'),  # San Diego - should be local
        ('10001', 'New York', 'United States'),    # NYC - not local
        ('91765', 'California', 'United States'),  # Diamond Bar - local
        ('', 'California', 'United States'),       # No zip - not local
        ('90024', 'California', 'China'),          # Wrong country - not local
    ]
    
    df = pd.DataFrame(test_data, columns=['Zip', 'State', 'Country'])
    df = add_is_local_to_df(df)
    
    print("\nResults:")
    print(df.to_string())

