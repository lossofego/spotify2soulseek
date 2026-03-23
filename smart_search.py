# smart search - try different query variations to find tracks on soulseek
# because soulseek search is picky and literal

import re


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
    
    return unique[:8]


def clean_text(text):
    if not text:
        return ""
    
    # remove junk in parens/brackets
    text = re.sub(r'\s*\([^)]*(?:remaster|version|anniversary|deluxe|edition|bonus)[^)]*\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\[[^\]]*(?:remaster|version|anniversary|deluxe|edition|bonus)[^\]]*\]', '', text, flags=re.IGNORECASE)
    
    # normalize quotes
    text = text.replace(''', "'").replace(''', "'").replace('"', '"').replace('"', '"')
    
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
    
    # common aliases
    aliases = {
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
    
    if lower in aliases:
        vars.extend(aliases[lower])
    
    return vars


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
    
    return vars


def score_result(filename, artist, title):
    """score how well a result matches - higher = better"""
    fn = filename.lower()
    art = artist.lower()
    ttl = title.lower()
    
    score = 0
    
    art_words = art.split()
    ttl_words = ttl.split()
    
    # artist word matches
    for w in art_words:
        if len(w) > 2 and w in fn:
            score += 10
    
    # full artist name
    if art in fn:
        score += 25
    
    # title word matches
    for w in ttl_words:
        if len(w) > 2 and w in fn:
            score += 10
    
    # full title
    ttl_clean = remove_featured(ttl)
    if ttl_clean in fn:
        score += 30
    elif ttl in fn:
        score += 25
    
    # penalize weird extra words
    fn_words = set(re.findall(r'\b\w{4,}\b', fn))
    expected = set(art_words + ttl_words)
    ignore = {'flac', 'mp3', 'wav', 'ogg', 'feat', 'featuring', 'remix', 'remaster', 'remastered'}
    unexpected = fn_words - expected - ignore
    score -= len(unexpected) * 2
    
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
    ]
    
    for artist, title in tests:
        print(f"\n{'='*60}")
        print(f"Artist: {artist}")
        print(f"Title: {title}")
        print("Queries:")
        for i, q in enumerate(generate_search_queries(artist, title), 1):
            print(f"  {i}. {q}")
