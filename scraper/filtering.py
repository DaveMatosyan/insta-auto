"""
Mechanical pre-filter — cut obvious non-buyers before Gemini scoring.
"""

import re

FEMALE_NAMES = {
    'jessica', 'sarah', 'maria', 'bella', 'nayla', 'bruna', 'claudia', 'sonya',
    'michelle', 'julia', 'grace', 'maddy', 'dawn', 'kaela', 'rhia', 'nita',
    'mae', 'yaneth', 'anna', 'emma', 'olivia', 'sophia', 'ava', 'mia',
    'isabella', 'emily', 'abigail', 'ella', 'chloe', 'lily', 'hannah', 'natalie',
    'samantha', 'victoria', 'madison', 'elizabeth', 'avery', 'scarlett', 'aria',
    'penelope', 'layla', 'riley', 'zoey', 'nora', 'camila', 'elena', 'luna',
    'savannah', 'aubrey', 'brooklyn', 'leah', 'zoe', 'stella', 'hazel', 'ellie',
    'paisley', 'audrey', 'skylar', 'violet', 'claire', 'bella', 'lucy', 'aaliyah',
    'caroline', 'genesis', 'emilia', 'kennedy', 'maya', 'willow', 'kinsley',
    'naomi', 'ariana', 'ruby', 'eva', 'serenity', 'autumn', 'adeline', 'hailey',
    'gianna', 'valentina', 'isla', 'eliana', 'quinn', 'nevaeh', 'ivy', 'sadie',
    'piper', 'lydia', 'alexa', 'josie', 'andrea', 'gabriella', 'alejandra',
    'daniela', 'fernanda', 'paola', 'valeria', 'mariana', 'catalina', 'tatiana',
    'priya', 'aisha', 'fatima', 'yasmin', 'lina', 'nina', 'tara', 'diana',
    'laura', 'paula', 'sandra', 'monica', 'carmen', 'rosa', 'angela', 'lisa',
    'jennifer', 'amanda', 'stephanie', 'heather', 'ashley', 'brittany', 'kelsey',
    'megan', 'rachel', 'rebecca', 'katherine', 'amber', 'nicole', 'tiffany',
    'crystal', 'vanessa', 'bianca', 'jasmine', 'alicia', 'veronica', 'kathleen',
}

FEMALE_KEYWORDS = {
    'girl', 'queen', 'mama', 'babe', 'princess', 'goddess', 'gurl', 'diva',
    'lady', 'chica', 'miss', 'missy', 'wifey', 'sissy', 'barbie', 'dolly',
}

BRAND_KEYWORDS = {
    'shop', 'store', 'brand', 'official', 'media', 'agency', 'studio',
    'photography', 'magazine', 'daily', 'news', 'memes', 'repost', 'fanpage',
    'clothing', 'apparel', 'boutique', 'fitness_brand', 'supplements',
    'coaching', 'nutrition', 'mealprep', 'podcast', 'radio',
}

COMPETITOR_BIO_KEYWORDS = {
    'ifbb', 'npc', 'bikini pro', 'figure pro', 'wellness pro',
    'fitness competitor', 'bodybuilding', 'physique', 'wbff',
    'olympia', 'arnold classic', 'prep coach',
}


def pre_filter_profile(profile, comment=''):
    """
    Mechanical pre-filter. Returns (keep, reason) tuple.
    keep=True means send to Gemini, keep=False means skip.
    """
    username = profile.get('username', '').lower()
    fullname = profile.get('fullname', '').lower()
    bio = profile.get('bio', '').lower()
    followers = profile.get('followers', 0)
    following = profile.get('following', 0)
    posts = profile.get('posts', 0)
    has_pfp = profile.get('has_custom_pfp', False)

    # BOT: no followers, no following, no pfp
    if followers == 0 and following == 0 and not has_pfp:
        return False, "bot (0/0/no pfp)"

    # BIG CREATOR: 50k+ followers = they're a creator, not buyer
    if followers >= 50000:
        return False, f"big creator ({followers} followers)"

    # FEMALE NAME in username
    username_clean = re.sub(r'[_.\d]+', ' ', username).strip()
    for name in FEMALE_NAMES:
        if name in username_clean.split() or username_clean.startswith(name):
            return False, f"female name '{name}' in username"

    # FEMALE NAME in fullname
    fullname_words = fullname.split()
    for name in FEMALE_NAMES:
        if name in fullname_words:
            return False, f"female name '{name}' in fullname"

    # FEMALE KEYWORDS in username
    for kw in FEMALE_KEYWORDS:
        if kw in username:
            return False, f"female keyword '{kw}' in username"

    # BRAND/BUSINESS
    for kw in BRAND_KEYWORDS:
        if kw in username:
            return False, f"brand keyword '{kw}' in username"

    # FITNESS COMPETITOR in bio
    for kw in COMPETITOR_BIO_KEYWORDS:
        if kw in bio:
            return False, f"competitor keyword '{kw}' in bio"

    # FEMALE BIO signals
    female_bio_signals = ['she/her', 'mom of', 'mother of', 'wife of', 'wifey',
                          'nail tech', 'lash tech', 'esthetician', 'makeup artist',
                          'model ', 'actress', 'dancer', 'onlyfans.com']
    for sig in female_bio_signals:
        if sig in bio:
            return False, f"female bio signal '{sig}'"

    return True, "passed"
