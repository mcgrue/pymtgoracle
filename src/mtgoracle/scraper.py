from BeautifulSoup import BeautifulSoup, NavigableString, Tag
from urllib import urlencode
import os.path
import requests
import string

URL_BASE = 'http://magiccards.info'


def scrape_all():
    from mtgoracle.dbengine import dbPath, get_engine
    from mtgoracle.model import metadata
    dbbak = dbPath + '.bak'
    if os.path.exists(dbbak):
        os.remove(dbbak)
    if os.path.exists(dbPath):
        os.rename(dbPath, dbbak)
    engine = get_engine(path=dbPath, echo=False)
    metadata.create_all(bind=engine)  # @UndefinedVariable @IgnorePep8
    DBSession.configure(bind=engine)
    setdicts = scrape_setdicts()
    for setdict in setdicts:
        cset = CardSet(**setdict)
        DBSession.add(cset)
        print cset
        cardtuples = cardandprints_from_setcode(cset.code)
        for carddict, printdict in cardtuples:
            card = DBSession.query(Card).\
                   filter_by(name=carddict['name']).first()
            if card is None:
                typestrs = carddict.pop('types')
                stypestrs = carddict.pop('subtypes')
                card = Card(**carddict)
                DBSession.add(card)
                print card
                for typestr in typestrs:
                    ctype = DBSession.query(CardType).\
                            filter_by(name=typestr).first()
                    if ctype is None:
                        ctype = CardType(name=typestr)
                        DBSession.add(ctype)
                        print ctype
                    card.types.append(ctype)
                for stypestr in stypestrs:
                    cstype = DBSession.query(CardSubtype).\
                                filter_by(name=stypestr).first()
                    if cstype is None:
                        cstype = CardSubtype(name=stypestr)
                        DBSession.add(cstype)
                        print cstype
                    card.subtypes.append(cstype)
            printing = CardPrinting(**printdict)
            printing.setcode = cset.code
            printing.cardname = card.name
            DBSession.add(printing)
            print printing
    DBSession.commit()


def scrape_setdicts():
    req = requests.get(URL_BASE + '/sitemap.html')
    soup = BeautifulSoup(req.content)
    en_anchor = soup.find('a', {'name': 'en'})
    en_table = en_anchor.findNext('table')
    en_setlinks = en_table.findAll('a')
    return [setdict_from_setlink(setlink) for setlink in en_setlinks]


def setdict_from_setlink(setlink):
    setdict = {
        'name': setlink.text,
        'code': setlink.parent.find('small').text,
        'link': URL_BASE + setlink['href']}
    blockli = setlink.findParents('li')[-1]
    setdict['block'] = blockli.contents[0]
    return setdict


def scrape_printdicts(setcode):
    querymap = {'q': '++e:' + setcode + '/en',
                'v': 'spoiler',
                's': 'issue'}
    spoilerlink = '/query?' + urlencode(querymap)
    req = requests.get(URL_BASE + spoilerlink)
    soup = BeautifulSoup(req.content)
    pspans = soup.findAll('span')
    return [printdict_from_printspan_and_setcode(psp, setcode) for psp in pspans]


def printdict_from_printspan_and_setcode(pspan, setcode):
    name = pspan.text
    cardlink = URL_BASE + pspan.find('a')['href']
    numstr = cardlink.split('/')[-1].replace('.html', '')
    if numstr[-1] in string.lowercase:
        variant = string.lowercase.index(numstr[-1]) + 1
        numstr = numstr[:-1]
    else:
        variant = -1
    rulesline = pspan.findNextSibling('p', {'class': 'ctext'})
    typecostline = rulesline.findPreviousSibling('p')
    rarityline = typecostline.findPreviousSibling('p')
    flavorline = rulesline.findNextSibling('p')
    flavor = ['\n' if isinstance(f, Tag) and f.name == 'br' else f for f in flavorline.findAll('i')[0].contents]
    artline = flavorline.findNextSibling('p')
    printing = {'setcode': setcode,
            'link': cardlink,
            'number': int(numstr),
            'variant': variant,
            'rarity': unicode(rarityline.findNext('i').text) if
                                rarityline else u'Special',
            'flavor': u''.join(flavor) if len(flavor) > 0 else None,
            'artist': unicode(artline.text).replace('Illus. ', '')}
    rules = [rl for rl in rulesline.find('b').contents if
             isinstance(rl, NavigableString)]
    typeline, costline = [l.strip() for l in typecostline.text.split(',')]
    types = typeline.split()
    if '/' in types[-1]:
        powr, tgh = types[-1].split('/')
        try:
            powr = int(powr)
        except ValueError:
            pass
        try:
            tgh = int(tgh)
        except ValueError:
            pass
        types = types[:-1]
    else:
        powr, tgh = None, None
    if name == u'1996 World Champion':
        suptypes = [u'Legendary', u'Creature']
        subtypes = []
    elif name == u'Shichifukujin Dragon':
        suptypes = [u'Creature']
        subtypes = [u'Dragon']
    elif name == u'Old Fogey':
        suptypes = ['Creature']
        subtypes = ['Dinosaur']
    elif u'Enchant' in types:
        suptypes = [u'Enchantment']
        subtypes = [u'Aura']
    elif u'\u2014' in types:
        i = types.index(u'\u2014')
        suptypes = types[:i]
        subtypes = types[i + 1:]
    else:
        suptypes = types
        subtypes = []
    if u'Legend' in subtypes:
        subtypes.remove(u'Legend')
        suptypes.append(u'Legendary')
    if u'(Loyalty:' in subtypes:
        i = subtypes.index(u'(Loyalty:')
        loyalty = int(subtypes[i + 1].strip(')'))
        subtypes = subtypes[:i]
    else:
        loyalty = None
    if costline == u'':
        cost, cmc = ('', 0)
    elif '(' in costline:
        cost, cmc = costline.split()
        cmc = int(cmc.strip('()'))
    else:
        cost, cmc = (costline, 0)
    card = {'name': unicode(name),
            'rules': [unicode(r) for r in rules],
            'power': powr,
            'toughness': tgh,
            'types': [unicode(t) for t in suptypes],
            'subtypes': [unicode(t) for t in subtypes],
            'cost': unicode(cost),
            'cmc': cmc,
            'loyalty': loyalty}
    printing.update(card)
    return printing


if __name__ == '__main__':
    scrape_all()
