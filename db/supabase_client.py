"""
Shared Supabase client for the insta-auto project.
All modules import `supabase` from here.
"""

from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
