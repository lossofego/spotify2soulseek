# smart search - try different query variations to find tracks on soulseek
# because soulseek search is picky and literal
#
# v2: adds unicode transliteration, path-aware scoring, bitrate validation

import re
import os
import json
import logging

logger = logging.getLogger(__name__)

# Try to import unidecode for transliteration
try:
    from unidecode import unidecode
    HAS_UNIDECODE = True
except ImportError:
    HAS_UNIDECODE = False
    logger.info("unidecode not installed — unicode transliteration disabled. pip install unidecode")


def generate_search_queries(artist, title):
    """generate multiple search queries, returns list in order of preference"""
    queries = []

    artist_clean = clean_text(artist)
    title_clean = clean_text(title)

    artist_vars = get_artist_variations(artist_clean)
    title_vars = get_title_variations(title_clean)

    # start with clean version
    queries.append(f"{artist_clean} {title_clean}")

    # try without feat. artists
    title_no_feat = remove_featured(title_clean)
    if title_no_feat != title_clean:
        queries.append(f"{artist_clean} {title_no_feat}")

    # unicode transliteration — catch Björk→Bjork, Sigur Rós→Sigur Ros, etc.
    artist_ascii = transliterate(artist_clean)
    title_ascii = transliterate(title_clean)
    title_no_feat_ascii = transliterate(title_no_feat)

    if artist_ascii != artist_clean or title_ascii != title_clean:
        queries.append(f"{artist_ascii} {title_ascii}")
    if artist_ascii != artist_clean and title_no_feat_ascii != title_no_feat:
        queries.append(f"{artist_ascii} {title_no_feat_ascii}")

    # artist variations
    for av in artist_vars:
        if av != artist_clean:
            queries.append(f"{av} {title_clean}")
            if title_no_feat != title_clean:
                queries.append(f"{av} {title_no_feat}")

    # title variations
    for tv in title_vars:
        if tv != title_clean and tv != title_no_feat:
            queries.append(f"{artist_clean} {tv}")

    # just title if it's unique enough
    if len(title_clean.split()) >= 3:
        queries.append(title_clean)

    # artist first word + title (for "The X" -> "X")
    first = artist_clean.split()[0] if artist_clean else ""
    if first and first.lower() not in ['the', 'a', 'an']:
        queries.append(f"{first} {title_no_feat}")

    # dedupe while keeping order
    seen = set()
    unique = []
    for q in queries:
        q_norm = q.lower().strip()
        if q_norm and q_norm not in seen:
            seen.add(q_norm)
            unique.append(q)

    return unique[:10]  # bumped from 8 to 10 to accommodate transliteration variants


def transliterate(text):
    """
    Convert unicode text to ASCII equivalent.
    Björk → Bjork, Sigur Rós → Sigur Ros, Mötley Crüe → Motley Crue,
    Ásgeir → Asgeir, 椎名林檎 → Jia Ming Lin Guo (rough romanization)
    """
    if not text or not HAS_UNIDECODE:
        return text

    ascii_text = unidecode(text)

    # unidecode can sometimes produce empty strings or just whitespace
    if not ascii_text.strip():
        return text

    # Clean up any double spaces from conversion
    ascii_text = ' '.join(ascii_text.split())

    return ascii_text


def clean_text(text):
    if not text:
        return ""

    # remove junk in parens/brackets
    text = re.sub(r'\s*\([^)]*(?:remaster|version|anniversary|deluxe|edition|bonus)[^)]*\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\[[^\]]*(?:remaster|version|anniversary|deluxe|edition|bonus)[^\]]*\]', '', text, flags=re.IGNORECASE)

    # normalize quotes
    text = text.replace('\u2018', "'").replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"')

    # strip special chars
    text = re.sub(r'[^\w\s\'-]', ' ', text)
    text = ' '.join(text.split())

    return text.strip()


def remove_featured(title):
    """strip (feat. X) etc from title"""
    patterns = [
        r'\s*\(feat\.?\s+[^)]+\)',
        r'\s*\(ft\.?\s+[^)]+\)',
        r'\s*\(featuring\s+[^)]+\)',
        r'\s*\(with\s+[^)]+\)',
        r'\s*\[feat\.?\s+[^\]]+\]',
        r'\s*\[ft\.?\s+[^\]]+\]',
        r'\s*feat\.?\s+.+$',
        r'\s*ft\.?\s+.+$',
        r'\s*featuring\s+.+$',
    ]
    for p in patterns:
        title = re.sub(p, '', title, flags=re.IGNORECASE)
    return title.strip()


def get_artist_variations(artist):
    """try different artist name spellings"""
    vars = [artist]
    if not artist:
        return vars

    lower = artist.lower()

    # --- Programmatic rules ---

    # the prefix
    if lower.startswith('the '):
        vars.append(artist[4:])
    else:
        vars.append(f"The {artist}")

    # & vs and
    if ' & ' in artist:
        vars.append(artist.replace(' & ', ' and '))
    if ' and ' in lower:
        vars.append(re.sub(r' and ', ' & ', artist, flags=re.IGNORECASE))
    if ' + ' in artist:
        vars.append(artist.replace(' + ', ' and '))
        vars.append(artist.replace(' + ', ' & '))

    # periods in names (B.I.G. -> BIG)
    if '.' in artist:
        no_dots = artist.replace('.', '')
        if no_dots != artist:
            vars.append(no_dots)
        spaced = re.sub(r'\.(\w)', r' \1', artist).replace('.', '')
        if spaced != artist and spaced != no_dots:
            vars.append(spaced)

    # DJ prefix — strip it if present to search without
    if lower.startswith('dj '):
        vars.append(artist[3:])

    # MC prefix
    if lower.startswith('mc '):
        vars.append(artist[3:])

    # Lastname, Firstname for classical/jazz
    # Only try if it looks like "Firstname Lastname" (exactly 2 words, both 3+ chars, capitalized)
    words = artist.split()
    if (len(words) == 2 and len(words[0]) >= 3 and len(words[1]) >= 3
            and words[0][0].isupper() and words[1][0].isupper()):
        vars.append(f"{words[1]}, {words[0]}")
        vars.append(f"{words[1]} {words[0]}")

    # Transliterated variant
    ascii_artist = transliterate(artist)
    if ascii_artist != artist:
        vars.append(ascii_artist)

    # --- Hardcoded aliases for common mismatches ---
    aliases = _load_aliases()
    if lower in aliases:
        vars.extend(aliases[lower])

    return vars


def _load_aliases():
    """
    Load artist aliases. Checks for external aliases.json first,
    falls back to built-in dict.
    """
    # Check for user-provided aliases file next to the script
    for search_dir in [os.path.dirname(os.path.abspath(__file__)),
                       os.path.expanduser('~')]:
        alias_path = os.path.join(search_dir, 'aliases.json')
        if os.path.exists(alias_path):
            try:
                with open(alias_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Normalize keys to lowercase
                return {k.lower(): v for k, v in data.items()}
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load aliases.json: {e}")

    # Built-in aliases
    return {
        'biggie smalls': ['notorious big', 'notorious b.i.g.', 'the notorious b.i.g.'],
        'notorious big': ['biggie smalls', 'biggie', 'notorious b.i.g.'],
        'notorious b.i.g.': ['biggie smalls', 'biggie', 'notorious big'],
        'snoop dogg': ['snoop doggy dogg', 'snoop'],
        'snoop doggy dogg': ['snoop dogg', 'snoop'],
        'puff daddy': ['p diddy', 'diddy', 'puffy', 'sean combs'],
        'p diddy': ['puff daddy', 'diddy', 'puffy'],
        'diddy': ['puff daddy', 'p diddy', 'puffy'],
        'kanye west': ['ye', 'kanye'],
        'ye': ['kanye west', 'kanye'],
        '2pac': ['tupac', 'tupac shakur', 'makaveli'],
        'tupac': ['2pac', 'tupac shakur', 'makaveli'],
        '50 cent': ['fifty cent', '50cent'],
        'jay-z': ['jay z', 'jayz', 'hova'],
        'jay z': ['jay-z', 'jayz'],
        'eminem': ['slim shady', 'marshall mathers'],
        'prince': ['the artist formerly known as prince', 'tafkap'],
        'led zeppelin': ['led zep', 'zeppelin'],
        'pink floyd': ['floyd'],
        'ac/dc': ['acdc', 'ac dc'],
        'guns n roses': ["guns n' roses", 'gnr', 'guns and roses'],
        "guns n' roses": ['guns n roses', 'gnr'],
        'red hot chili peppers': ['rhcp', 'chili peppers'],
        'rage against the machine': ['ratm', 'rage'],
        'system of a down': ['soad', 'system'],
        'queens of the stone age': ['qotsa'],
        'nine inch nails': ['nin'],
        'n.w.a': ['nwa', 'n.w.a.'],
        'nwa': ['n.w.a', 'n.w.a.'],
        'run-d.m.c.': ['run dmc', 'rundmc'],
        'run dmc': ['run-d.m.c.', 'run-dmc'],
        'a tribe called quest': ['atcq', 'tribe called quest'],
        'wu-tang clan': ['wu tang clan', 'wu-tang', 'wu tang'],
        'outkast': ['out kast', 'outcast'],
        'beastie boys': ['beasties'],
        'de la soul': ['de la'],
    }


def get_title_variations(title):
    vars = [title]
    if not title:
        return vars

    lower = title.lower()

    # strip remaster/version junk
    suffixes = [
        r'\s*-\s*remaster(ed)?.*$',
        r'\s*-\s*\d{4}\s*remaster.*$',
        r'\s*\(remaster(ed)?\).*$',
        r'\s*\(\d{4}\s*remaster.*\)$',
        r'\s*-\s*single\s*version.*$',
        r'\s*-\s*album\s*version.*$',
        r'\s*-\s*radio\s*edit.*$',
        r'\s*\(radio\s*edit\)$',
        r'\s*-\s*original.*$',
        r'\s*\(original.*\)$',
    ]
    for pat in suffixes:
        cleaned = re.sub(pat, '', title, flags=re.IGNORECASE).strip()
        if cleaned and cleaned != title:
            vars.append(cleaned)

    # part/pt variations
    if re.search(r'\bpart\s*(\d+)', lower):
        vars.append(re.sub(r'\bpart\s*(\d+)', r'pt \1', title, flags=re.IGNORECASE))
    if re.search(r'\bpt\.?\s*(\d+)', lower):
        vars.append(re.sub(r'\bpt\.?\s*(\d+)', r'part \1', title, flags=re.IGNORECASE))

    # & vs and
    if ' & ' in title:
        vars.append(title.replace(' & ', ' and '))
    if ' and ' in lower:
        vars.append(re.sub(r' and ', ' & ', title, flags=re.IGNORECASE))

    # apostrophes
    if "'" in title:
        vars.append(title.replace("'", ""))

    # roman numerals
    romans = {'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5',
              'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10'}
    for rom, num in romans.items():
        if re.search(rf'\b{rom}\b', lower):
            vars.append(re.sub(rf'\b{rom}\b', num, title, flags=re.IGNORECASE))

    # transliterated variant
    ascii_title = transliterate(title)
    if ascii_title != title:
        vars.append(ascii_title)

    return vars


# ============================================================================
# Result scoring — determines which search result is the "best" match
# ============================================================================

def score_result(result_file, artist, title, album=None, duration_ms=0, format_preference="mp3"):
    """
    Score how well a search result matches what we're looking for.
    Higher = better.

    Args:
        result_file: dict from slskd search results, containing at minimum:
                     'filename' (str), and optionally 'size' (int bytes),
                     'bitRate' (int), 'sampleRate' (int), 'bitDepth' (int),
                     'length' (int seconds)
        artist: target artist name
        title: target track title
        album: target album name (from Spotify metadata, optional)
        duration_ms: target duration in ms (from Spotify metadata, 0 if unknown)
        format_preference: "mp3" or "lossless"

    Returns:
        int: score (higher = better match)
    """
    # Get the full file path (slskd returns this as 'filename' which includes dirs)
    filepath = result_file.get('filename', '')
    fn = filepath.lower()

    # Split into directory path and actual filename
    fn_parts = filepath.replace('\\', '/').split('/')
    actual_filename = fn_parts[-1].lower() if fn_parts else fn
    parent_dir = fn_parts[-2].lower() if len(fn_parts) >= 2 else ''
    grandparent_dir = fn_parts[-3].lower() if len(fn_parts) >= 3 else ''

    art = artist.lower()
    ttl = title.lower()
    alb = album.lower() if album else ''

    score = 0

    # --- Core matching: artist + title in filename ---

    art_words = art.split()
    ttl_words = ttl.split()

    # artist word matches in filename
    for w in art_words:
        if len(w) > 2 and w in actual_filename:
            score += 10

    # full artist name in filename
    if art in actual_filename:
        score += 25

    # title word matches in filename
    for w in ttl_words:
        if len(w) > 2 and w in actual_filename:
            score += 10

    # full title match
    ttl_clean = remove_featured(ttl)
    if ttl_clean in actual_filename:
        score += 30
    elif ttl in actual_filename:
        score += 25

    # --- Path-aware scoring: album + artist in directory structure ---

    # Artist in parent/grandparent directory (common: Artist/Album/Track.flac)
    if art in parent_dir or art in grandparent_dir:
        score += 15

    # Album matching against directory names
    if alb:
        alb_words = [w for w in alb.split() if len(w) > 2]

        # Full album name in parent directory
        if alb in parent_dir:
            score += 30
        elif alb in grandparent_dir:
            score += 20
        else:
            # Partial album word matches in directory
            dir_album_hits = sum(1 for w in alb_words if w in parent_dir)
            if alb_words and dir_album_hits >= len(alb_words) * 0.6:
                score += 15

    # Year extraction from directory path — bonus if it matches
    # Look for 4-digit year in directory names
    year_matches = re.findall(r'\b(19[6-9]\d|20[0-2]\d)\b', parent_dir + ' ' + grandparent_dir)
    if year_matches and duration_ms > 0:
        # We don't have release year directly, but we can use it as a positive signal
        # that this is a well-organized library (better quality source)
        score += 5

    # Track number in filename is a good sign (organized library)
    if re.match(r'^\d{1,2}[\s._-]', actual_filename):
        score += 5

    # --- Format and quality scoring ---

    file_ext = os.path.splitext(actual_filename)[1].lower()
    bitrate = result_file.get('bitRate', 0)
    sample_rate = result_file.get('sampleRate', 0)
    file_size = result_file.get('size', 0)
    file_length = result_file.get('length', 0)  # seconds

    # Format preference
    lossless_exts = {'.flac', '.wav', '.alac', '.ape', '.wv'}
    lossy_exts = {'.mp3', '.ogg', '.opus', '.m4a', '.aac', '.wma'}

    is_lossless = file_ext in lossless_exts
    is_lossy = file_ext in lossy_exts

    if format_preference == "lossless":
        if is_lossless:
            score += 20
        elif is_lossy:
            score += 5  # still usable, just not preferred
    else:  # mp3 preference
        if file_ext == '.mp3':
            score += 15
        elif is_lossless:
            score += 10  # lossless is still good even in mp3-preference mode
        elif is_lossy:
            score += 5

    # Bitrate quality scoring
    if is_lossy and bitrate > 0:
        if bitrate >= 320:
            score += 15
        elif bitrate >= 256:
            score += 10
        elif bitrate >= 192:
            score += 5
        elif bitrate < 128:
            score -= 20  # garbage quality

    # --- Transcode detection ---
    # A FLAC that's suspiciously small relative to duration is likely a transcode
    if is_lossless and file_size > 0 and file_length > 0:
        # Expected FLAC size: ~1000 kbps for CD quality (44.1kHz/16bit stereo)
        # A real FLAC is typically 700-1400 kbps
        # A transcoded FLAC (from 128kbps mp3) would be ~300-500 kbps
        actual_kbps = (file_size * 8) / (file_length * 1000)

        if actual_kbps < 500:
            # Very suspicious — likely transcoded from low-quality lossy
            score -= 25
            logger.debug(f"Suspected transcode: {actual_filename} ({actual_kbps:.0f} kbps FLAC)")
        elif actual_kbps < 650:
            # Possibly transcoded, mild penalty
            score -= 10

    # Use Spotify duration for additional transcode/mismatch detection
    if duration_ms > 0 and file_length > 0:
        spotify_seconds = duration_ms / 1000
        # Allow 5 seconds tolerance for different versions/encoding
        duration_diff = abs(spotify_seconds - file_length)

        if duration_diff <= 5:
            score += 10  # duration matches well — good sign
        elif duration_diff <= 15:
            score += 0   # close enough, neutral
        elif duration_diff <= 60:
            score -= 10  # might be a different version
        else:
            score -= 30  # way off — probably wrong track entirely

    # --- Penalty for mismatches ---

    # Penalize unexpected extra words in filename (not artist/title/album words)
    fn_words = set(re.findall(r'\b\w{4,}\b', actual_filename))
    expected = set(art_words + ttl_words)
    if alb:
        expected.update(alb.split())
    ignore = {'flac', 'mp3', 'wav', 'ogg', 'opus', 'feat', 'featuring',
              'remix', 'remaster', 'remastered', 'kbps', 'vinyl', 'lossless',
              'track', 'disc', 'disk', 'album'}
    unexpected = fn_words - expected - ignore
    score -= len(unexpected) * 2

    # Heavy penalty for remix/live/acoustic unless the original title has it
    remix_indicators = ['remix', 'bootleg', 'mashup', 'dub mix', 'club mix']
    live_indicators = ['live', 'concert', 'session', 'unplugged', 'acoustic']

    for indicator in remix_indicators:
        if indicator in actual_filename and indicator not in ttl:
            score -= 30

    for indicator in live_indicators:
        if indicator in actual_filename and indicator not in ttl:
            score -= 15

    # Skip non-audio files entirely
    non_audio = {'.jpg', '.jpeg', '.png', '.gif', '.txt', '.nfo', '.log',
                 '.cue', '.m3u', '.pdf', '.sfv', '.md5'}
    if file_ext in non_audio:
        score -= 1000

    return score


# quick test
if __name__ == "__main__":
    tests = [
        ("The Notorious B.I.G.", "Mo Money Mo Problems (feat. Puff Daddy & Mase)"),
        ("Guns N' Roses", "Sweet Child O' Mine"),
        ("AC/DC", "Back in Black"),
        ("OutKast", "Hey Ya!"),
        ("Jay-Z", "99 Problems"),
        ("2Pac", "California Love (feat. Dr. Dre)"),
        ("Red Hot Chili Peppers", "Under the Bridge - 2017 Remaster"),
        ("Led Zeppelin", "Stairway to Heaven"),
        ("Björk", "Army of Me"),
        ("Sigur Rós", "Hoppípolla"),
        ("Mötley Crüe", "Kickstart My Heart"),
        ("DJ Shadow", "Building Steam with a Grain of Salt"),
    ]

    for artist, title in tests:
        print(f"\n{'='*60}")
        print(f"Artist: {artist}")
        print(f"Title: {title}")
        print("Queries:")
        for i, q in enumerate(generate_search_queries(artist, title), 1):
            print(f"  {i}. {q}")

    # Test scoring
    print(f"\n{'='*60}")
    print("Scoring test:")
    fake_results = [
        {
            'filename': '\\Music\\Pink Floyd\\1973 - The Dark Side of the Moon\\03 - Time.flac',
            'size': 35_000_000, 'bitRate': 0, 'sampleRate': 44100, 'length': 413
        },
        {
            'filename': '\\random\\pink floyd time.mp3',
            'size': 8_000_000, 'bitRate': 320, 'sampleRate': 44100, 'length': 410
        },
        {
            'filename': '\\Music\\time_remix_2024.flac',
            'size': 5_000_000, 'bitRate': 0, 'sampleRate': 44100, 'length': 415
        },
    ]

    for r in fake_results:
        s = score_result(r, "Pink Floyd", "Time",
                        album="The Dark Side of the Moon", duration_ms=413000)
        print(f"  Score {s:4d}: {r['filename']}")
