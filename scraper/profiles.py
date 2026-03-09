"""
Profile data extraction — visit profiles and parse data, or parse API responses.
"""

from core.utils import human_delay


def parse_api_user(user: dict) -> dict:
    """
    Parse an Instagram API user object (from /api/v1/users/web_profile_info/)
    into our standard profile dict format.

    This is the same data we'd get from visiting a profile page, but
    obtained by intercepting the API call triggered on username hover.
    """
    followers = int(user.get('edge_followed_by', {}).get('count', 0) or 0)
    following = int(user.get('edge_follow', {}).get('count', 0) or 0)
    posts = int(user.get('edge_owner_to_timeline_media', {}).get('count', 0) or 0)
    pfp = user.get('profile_pic_url_hd') or user.get('profile_pic_url') or ''
    bio_links = user.get('bio_links') or []
    ext_link = user.get('external_url') or ''
    if not ext_link and bio_links:
        ext_link = bio_links[0].get('url') or bio_links[0].get('title') or ''
    username = user.get('username', '')
    return {
        'username': username,
        'profile_url': f'https://www.instagram.com/{username}/',
        'followers': followers,
        'following': following,
        'follow_ratio': round(following / max(followers, 1), 2),
        'posts': posts,
        'fullname': (user.get('full_name') or '')[:50],
        'bio': (user.get('biography') or '')[:150],
        'external_link': ext_link[:100],
        'is_private': bool(user.get('is_private', False)),
        'is_verified': bool(user.get('is_verified', False)),
        'has_story': False,
        'has_custom_pfp': bool(pfp and '44884218' not in pfp),
    }


def get_profile_data(page, username):
    """
    Visit a profile and extract raw data for AI scoring.

    Returns:
        dict with profile data, or None on error
    """
    try:
        page.goto(f"https://www.instagram.com/{username}/", wait_until="domcontentloaded", timeout=20000)
        human_delay(2, 3)

        profile = page.evaluate(r"""() => {
            const meta = document.querySelector('meta[name="description"]');
            let metaFollowers = 0, metaFollowing = 0, metaPosts = 0, metaName = '';
            if (meta) {
                const content = meta.getAttribute('content') || '';
                const fm = content.match(/([\d,.]+[KkMm]?)\s*Follower/);
                const gm = content.match(/([\d,.]+[KkMm]?)\s*Following/);
                const pm = content.match(/([\d,.]+[KkMm]?)\s*Post/);
                if (fm) metaFollowers = fm[1];
                if (gm) metaFollowing = gm[1];
                if (pm) metaPosts = pm[1];
                const nm = content.match(/from\s+(.+?)\s*\(@/);
                if (nm) metaName = nm[1].trim();
            }

            const stats = [];
            document.querySelectorAll('header li, header ul li').forEach(li => {
                const text = li.textContent.replace(/,/g, '');
                const num = parseInt(text.replace(/[^0-9]/g, ''));
                if (!isNaN(num)) stats.push(num);
            });

            let fullname = '';
            const titleMatch = document.title.match(/^(.+?)\s*\(@/);
            if (titleMatch) fullname = titleMatch[1].trim();
            if (!fullname && metaName) fullname = metaName;
            if (!fullname) {
                const headerSpans = document.querySelectorAll('header section span');
                for (const sp of headerSpans) {
                    const t = sp.textContent.trim();
                    if (t && t.length > 1 && t.length < 60
                        && !/^\d/.test(t) && !t.includes('follower') && !t.includes('following')
                        && !t.includes('post') && !t.includes('@') && !t.includes('http')
                        && !t.includes('Edit') && !t.includes('Follow')
                        && !/^\d+$/.test(t.replace(/[,.\s]/g, ''))) {
                        fullname = t;
                        break;
                    }
                }
            }

            let bio = '';
            if (meta) {
                const content = meta.getAttribute('content') || '';
                const bioParts = content.split(' - ');
                if (bioParts.length > 1) {
                    const lastPart = bioParts[bioParts.length - 1].trim();
                    if (!lastPart.startsWith('See Instagram')) {
                        bio = lastPart.replace(/^[""]|[""]$/g, '').trim();
                    }
                }
            }
            if (!bio) {
                const allSpans = document.querySelectorAll('header span');
                for (const sp of allSpans) {
                    const t = sp.textContent.trim();
                    if (t && t.length > 10 && t.length < 300
                        && !/^\d/.test(t) && !t.includes('follower') && !t.includes('following')
                        && t !== fullname && !t.includes('Threads')
                        && !t.includes('Edit profile') && !t.includes('Follow')) {
                        bio = t;
                        break;
                    }
                }
            }

            const linkEl = document.querySelector('a[href*="l.instagram.com"]') ||
                           document.querySelector('a[rel="me nofollow noopener noreferrer"]') ||
                           document.querySelector('header a[href^="http"]');
            const externalLink = linkEl ? linkEl.textContent.trim() : '';

            const bodyText = document.body.textContent;
            const isPrivate = bodyText.includes('This account is private') ||
                              bodyText.includes('This Account is Private');

            const isVerified = !!document.querySelector('svg[aria-label="Verified"]') ||
                               !!document.querySelector('span[title="Verified"]');

            const hasStory = !!document.querySelector('header canvas') ||
                             !!document.querySelector('header div[role="button"] img[draggable]');

            const pfpEl = document.querySelector('img[alt*="profile picture"]') ||
                          document.querySelector('img[data-testid="user-avatar"]') ||
                          document.querySelector('header img');
            const pfpUrl = pfpEl ? pfpEl.getAttribute('src') : '';
            const hasCustomPfp = pfpUrl && !pfpUrl.includes('44884218_345707102882519');

            return {
                stats: stats,
                metaFollowers: metaFollowers,
                metaFollowing: metaFollowing,
                metaPosts: metaPosts,
                fullname: fullname.substring(0, 100),
                bio: bio.substring(0, 300),
                externalLink: externalLink.substring(0, 200),
                isPrivate: isPrivate,
                isVerified: isVerified,
                hasStory: hasStory,
                hasCustomPfp: hasCustomPfp,
            };
        }""")

        def parse_num(val):
            if isinstance(val, (int, float)):
                return int(val)
            s = str(val).replace(',', '').strip()
            if not s:
                return 0
            if s[-1].lower() == 'k':
                return int(float(s[:-1]) * 1000)
            if s[-1].lower() == 'm':
                return int(float(s[:-1]) * 1000000)
            try:
                return int(s)
            except:
                return 0

        followers = parse_num(profile.get('metaFollowers', 0))
        following = parse_num(profile.get('metaFollowing', 0))
        posts = parse_num(profile.get('metaPosts', 0))
        fullname = profile.get('fullname', '')
        bio = profile.get('bio', '')
        external_link = profile.get('externalLink', '')
        is_private = profile.get('isPrivate', False)
        is_verified = profile.get('isVerified', False)
        has_story = profile.get('hasStory', False)
        has_custom_pfp = profile.get('hasCustomPfp', False)

        stats = profile.get('stats', [])
        if followers == 0 and len(stats) >= 2:
            posts = stats[0] if len(stats) >= 1 else 0
            followers = stats[1] if len(stats) >= 2 else 0
            following = stats[2] if len(stats) >= 3 else 0

        follow_ratio = round(following / max(followers, 1), 2)

        return {
            "username": username,
            "profile_url": f"https://www.instagram.com/{username}/",
            "followers": followers,
            "following": following,
            "follow_ratio": follow_ratio,
            "posts": posts,
            "fullname": fullname[:50],
            "bio": bio[:150],
            "external_link": external_link[:100],
            "is_private": is_private,
            "is_verified": is_verified,
            "has_story": has_story,
            "has_custom_pfp": has_custom_pfp,
        }

    except Exception as e:
        print(f"      Could not get data for @{username}: {e}")
        return None
