# -*- coding: utf-8 -*-
"""
Builds epub book out of Paul Graham's essays: http://paulgraham.com/articles.html

Original script: Ola Sitarska <ola@sitarska.com>
Improved version: Cristian Dinu <goc9000@gmail.com>

This script requires python-epub-library: http://code.google.com/p/python-epub-builder/
The checking facility requires epubcheck: http://code.google.com/p/epubcheck/
Embedding the 'Roots of Lisp' paper requires the programs ps2pdf and pdftoppm
to be installed.
"""

import os, base64, hashlib, imghdr, re, urllib2, genshi, shutil, epub, subprocess

from subprocess import Popen, PIPE
from genshi.template import MarkupTemplate
from BeautifulSoup import BeautifulSoup, Comment, Tag

ROOT_URL = 'http://www.paulgraham.com/'
BOOK_TITLE = "Paul Graham's Essays"
OUTPUT_FILE = BOOK_TITLE + '.epub'
OMIT_TRANSLATIONS = True
REMOVE_DEPRECATED_LINKS = True
INCLUDE_COMMENTS = True
INCLUDE_LINKS = True
INCLUDE_APPENDICES = True
INCLUDE_IMAGE_APPENDICES = True
INCLUDE_ROOTS_OF_LISP = False
CHECK_EPUB = True
KEEP_OUTPUT_DIR = False

# These articles will never be dowloaded as appendices (usually because they
# are ads, download, or extensive theory pages
FORCE_EXTERNAL_ARTICLES = [
    'hackpaint.html', 'piraha.html', 'arc.html', 'onlisp.html', 'acl.html',
    'onlisptext.html', 'filters.html', 'bbf.html', 'accgensub.html'
    ]

# These articles represent images, a separate category of appendices that may
# be treated differently
IMAGE_APPENDICES = [
    '04magnum.html', '1974-911s.html', '59eldorado.html', '75eldorado.html',
    'amcars.html', 'americangothic.html', 'baptism.html', 'bluebox.html',
    'creationofadam.html', 'denver.html', 'designedforwindows.html',
    'garage.html', 'ginevra.html', 'guggen.html', 'hunters.html', 'isetta.html',
    'largilliere-chardin.html', 'leonardo.html', 'matador.html',
    'montefeltro.html', 'nerdad.html', 'pantheon.html', 'pierced.html',
    'pilate.html', 'porsche695.html', 'sr71.html', 'symptg.html', 'tlbmac.html',
    'vwfront.html', 'womb.html', 'zero.html'
    ]

# Text for images representing titles (only the main title has an ALT attribute).
# So far these are needed only for one article.
TITLE_IMAGES = { 'paulgraham_2202_12135763': 'Guiding Philosophy',
                 'paulgraham_2202_12136436': 'Open Problems',
                 'paulgraham_2202_12137035': 'Little-Known Secrets',
                 'paulgraham_2202_12137782': 'Ideas Whose Time Has Returned',
                 'paulgraham_2202_12138764': 'Pitfalls and Gotchas' }

# These allow for the recognition of banners appearing right under the title
BANNER_ADS = ['Want to start a startup?', 'Watch how this essay was',
              'Like to build things?', 'The Suit is Back']

# Sections that contain these strings are ads and will be discarded
SECTION_ADS = [ "There can't be more than a couple thousand",
                "If you liked this, you may also like Hackers & Painters",
                "You'll find this essay and 14 others in Hackers & Painters"]

# Comments that contain any of these strings are ads and will be discared
COMMENT_ADS = [ 'Leave a tip', 'Winter Founders Program',
                'If you liked this', 'redditino.png' ]

SECTION_TEMPLATE = MarkupTemplate("""
<html xmlns="http://www.w3.org/1999/xhtml"
    xmlns:py="http://genshi.edgewall.org/">
<head>
  <title>${title}</title>
  <style type="text/css">
body { font-family: sans-serif; }
h1, h2 { font-variant: small-caps; color: #800000; }
blockquote { font-style: italic; }
a._local_link { background-color: #e0e0e0; }
a._external_link { }
img._embedded_page { border: 1px solid gray; }
${css}
  </style>
</head>
<body>
${text}
</body>
</html>
""")

# This keeps track over which are the main articles; this is initialized
# automatically later on.
MAIN_ARTICLES = [
    ]

class BookData:
    articles = None
    images = None
    unresolved = None
    toc = None
    
    main_articles = None
    
    def __init__(self):
        self.articles = {}
        self.images = {}
        self.unresolved = set()
        self.main_toc = []
        self.appendix_toc = []
        self.image_toc = []
        self.main_articles = set()

def readFile(filename):
    with open(filename, "rb") as f:
        return f.read()

def writeFile(filename, data):
    with open(filename, "wb") as f:
        f.write(data)

def htmlEntities(text):
    return text.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')

def isExternalUrl(url):
    return re.match("\\w+:", url) is not None

def cachedPageFilename(url):
    hsh = base64.b64encode(url, "()").replace('=','_')
    
    return "cache/{0}".format(hsh)

def getPage(url):
    if not os.path.exists("cache"):
        os.mkdir("cache")
    
    filename = cachedPageFilename(url)
    
    if os.path.isfile(filename):
        print "Retrieving {0} from cache".format(url)
        return readFile(filename)
    
    print "Downloading: {0}...".format(url)
    
    page = urllib2.urlopen(url).read()
    
    writeFile(filename, page)
    
    return page

def extractBody(page):
    return re.search("<body\\b[^>]*>.*?</body\\b[^>]*>", page, re.DOTALL).group(0)

def fixWeirdTags(page):
    page = re.sub("<(xa|ax|nota)\\s+",'<a class="_deprecated_link" ', page)
    page = re.sub("<ximg\\s+[^>]*>", '', page) # delete deprecated images
    
    return page

def fixXmpTags(page):
    def _convertXmp(match):
        return '<pre>' + htmlEntities(match.group(1)) + '</pre>'
    
    return re.sub("<xmp\\b[^>]*>(.*?)</xmp>", _convertXmp, page, 0, re.DOTALL | re.I)

def doAdhocFixes(page):
    def _adhocFix1(match):
        text = re.sub("<br><br>\\d+[.] ", '</li><li>', match.group(1))
        return '<ol><li>' + text + '</li></ol>'
    
    page = re.sub("<ol>\\s*1. (Catalogs are so expensive.*?)</ol>", _adhocFix1, page, 0, re.S)
    page = re.sub(" alt=\"Click to enlarge\"", '', page)

    CREDIT = 'Image: Casey Muller: Trevor Blackwell at Rehearsal Day, summer 2006'
    if CREDIT in page:
        pat = 'width=410 height=144 border=0 hspace=0 vspace=0></a>'
        pos1 = page.find(pat) + len(pat)
        pos = page.find(CREDIT)
        pos2 = page.rfind('<table', 0, pos)
        pos3 = len('</table>') + page.find('</table>', pos)
        
        credit_html = '<br><span style="font-size: 75%">' + CREDIT + "</span><br>"
        page = page[:pos1] + credit_html + page[pos1:pos2] + page[pos3:]
    
    if 'alt="Lisp for Web-Based Applications"' in page:
        text = getPage('http://lib.store.yahoo.net/lib/paulgraham/bbnexcerpts.txt')
        pat = 'BBN Labs in Cambridge, MA.<br><br></font>'
        pos = page.find(pat) + len(pat)
        
        bbn_html = "<pre>" + htmlEntities(text) + "</pre>"
        page = page[:pos] + bbn_html + page[pos:]
    
    return page

def removeBanners(page):
    idx1 = page.find('<font size=2 face="verdana"><table width=100%')
    if idx1 != -1:
        idx2 = page.find("</table>", idx1)
        if idx2 != -1:
            idx2 += len("</table>")
            is_ad = any((ad in page[idx1:idx2] for ad in BANNER_ADS))
            if is_ad:
                pat = re.compile("(?P<ad>(<p>|<br><br>)\\s*(<[!]--.*?-->)?\\s*)\\w+\\s+\\d{4}", re.DOTALL)
                m = pat.search(page, idx2)
                if m is not None:
                    page = page[:idx1] + page[m.end('ad'):]
        
    return page

def convertParagraphs(page):
    return re.sub("<p(\\s+[^>]*)?>", '<br/><br/>', page)

def extractTitle(page):
    return re.search('<title>([^<]*)</title>', page).group(1).strip()

def guessTitle(text):
    if text.startswith('(This is the first chapter of ANSI Common Lisp'):
        return 'Chapter 1 of Ansi Common Lisp'
    if text.startswith('(This is Chapter 2 of ANSI Common Lisp'):
        return 'Chapter 2 of Ansi Common Lisp'
    
    print '### ERROR: Cannot guess the title for this text: ###'
    print text[:400],'[...]'
    print '###'
    raise RuntimeError("Please modify the program accordingly")

def extractComments(page):
    def _collectComment(match, state):
        if not INCLUDE_COMMENTS:
            return ''
        
        text = match.group(1)
        if any(ad in text for ad in COMMENT_ADS):
            return ''
        
        pos = text.find('name="')
        if pos != -1:
            pos += len('name="')
            text = text[:pos] + 'deleted_' + text[pos:]
        
        state['comments'].append(text)
        
        return '<sup><a href="#_comment{0}">({0})</a></sup>'.format(len(state['comments']))
    
    pat_comments = re.compile("<!--(.*?)-->", re.DOTALL)
    
    state = dict()
    state['comments'] = []
    
    page = re.sub(pat_comments, lambda match : _collectComment(match, state), page)
    
    if len(state['comments']) > 0:
        # Insert comments at the end of body
        pos = page.find("</body")
        comments_html = ''.join('<br/><br /><a name="_comment{0}">({0})</a> {1}'.format(idx+1, comm) for idx, comm in enumerate(state['comments']))
        comments_div = '<div id="__comments"><br /><b>Comments and Edits</b>{0}</div>'.format(comments_html)
        
        page = page[:pos] + comments_div + page[pos:]
    
    return page

def preprocessPage(page):
    page = page.encode('ascii', 'xmlcharrefreplace')
    page = extractBody(page)
    page = fixWeirdTags(page)
    page = fixXmpTags(page)
    page = doAdhocFixes(page)
    page = removeBanners(page)
    page = convertParagraphs(page)
    page = extractComments(page)

    return page

def findTitleImage(soup):
    title_img = soup.find('img', { 'alt': lambda alt: alt is not None })
    if title_img is None:
        raise RuntimeError("Title img not found")
    
    return title_img

def isLinksSection(table):
    if table.find('a') is None or table.find('img') is None:
        return False
    
    for link in table.findAll('a'):
        font = link.parent
        if font.name != 'font' or font.get('size') != '2' or font.get('face') != 'verdana':
            return False
    
    for img in table.findAll('img'):
        if not (img['src'].endswith('trans_1x1.gif') or img['src'].startswith('http://ep.yimg.com/ca/I/paulgraham_')):
            return False
        
        w = 0 if img.get('width') is None else int(img['width'])
        h = 0 if img.get('height') is None else int(img['height'])
        
        if w > 20 or h > 20:
            return False
    
    return True

def rewriteLinksSection(dom, soup, links_table):
    links = []
    for fnt in links_table.findAll('font', {'size': '2', 'face':'verdana'}):
        if str(fnt).startswith('<font size="2" face="verdana"><a href="'):
            link = fnt.find('a')
            
            caption = link.getText('').strip()
            if caption.endswith(' Translation') and OMIT_TRANSLATIONS:
                continue
            
            links.append((link['href'], caption))
    
    links_table.decompose()
    
    if not INCLUDE_LINKS or len(links) == 0:
        return
    
    b = Tag(soup, 'b')
    b.string = 'Links'
    dom.append(b)
    
    ul = Tag(soup, 'ul')
    for url, caption in links:
        li = Tag(soup, 'li')
        a = Tag(soup, 'a', {'href': url})
        a.string = caption
        li.append(a)
        ul.append(li)
    
    dom.append(ul)

def isAdSection(table):
    text = table.getText(' ')
    if any(ad in text for ad in SECTION_ADS):
        return True
    
    return False

def isDisqusSection(table):
    return table.find('div', { 'id' : 'disqus_thread' }) is not None

def isEndSection(table):
    return table.find('hr') is not None and table.getText('').strip() == ''

def appendCustomSection(dom, soup, table):
    for tr in table.contents:
        for td in tr.contents:
            if td.get('width') is not None and int(td['width']) < 10:
                continue
            for img in td.findAll('img'):
                if img['src'].endswith('trans_1x1.gif'):
                    img.decompose()
            if len(td.contents) == 0:
                continue
            for item in td.contents:
                dom.append(item)
    
    table.decompose()

def embedRootsOfLispArticle(dom, soup):
    def _checkInstalled(name, cmdline, expected):
        try:
            out, err = Popen(cmdline, shell=False, stdout=PIPE, stderr=PIPE).communicate()
            out = (out + err).strip()
            if not out.startswith(expected):
                raise RuntimeError()
        except:
            raise RuntimeError(name + " does not appear to be installed")
    
    TEMP_DIR = 'temp_rootsoflisp'
    WIDTH = 800
    HEIGHT = 940*WIDTH / 600
    X = 176*WIDTH / 600
    Y = 170*WIDTH / 600
    DPI = 112*WIDTH / 600
    
    try:
        if not os.path.isdir(TEMP_DIR):
            os.mkdir(TEMP_DIR)
        
        data = getPage('http://lib.store.yahoo.net/lib/paulgraham/jmc.ps')
        ps_filename = os.path.join(TEMP_DIR, 'jmc.ps')
        writeFile(ps_filename, data)
        
        print "Checking all required programs are installed..."
        _checkInstalled('ps2pdf', ['ps2pdf'], 'Usage: ps2pdf')
        _checkInstalled('pdftoppm', ['pdftoppm', '-h'], 'pdftoppm version ')
        
        print "Converting to PDF..."
        pdf_filename = os.path.join(TEMP_DIR, 'jmc.pdf')
        subprocess.call(['ps2pdf', ps_filename, pdf_filename])
        
        print "Extracting page images..."
        page_filename = os.path.join(TEMP_DIR, 'jmc_page')
        subprocess.call(['pdftoppm', '-q', '-png',  '-r', str(DPI),
                         '-x', str(X), '-y', str(Y),
                         '-W', str(WIDTH), '-H', str(HEIGHT),
                         pdf_filename, page_filename])
        
        for i in xrange(1, 14):
            src = page_filename + '-{0:02d}.png'.format(i)
            dest = cachedPageFilename('jmc_paper/page{0}.png'.format(i))
            shutil.copyfile(src, dest)
        
        shutil.rmtree(TEMP_DIR, True)
        
        # Add embedded pages to the DOM
        center = Tag(soup, 'center')
        for i in xrange(1, 14):
            center.append(Tag(soup, 'br'))
            img = Tag(soup, 'img', { 'src': 'jmc_paper/page{0}.png'.format(i),
                                     'width': str(WIDTH), 'height': str(HEIGHT),
                                     'class': '_embedded_page' })
            center.append(img)
            center.append(Tag(soup, 'br'))
        
        dom.append(center)
    except RuntimeError as e:
        shutil.rmtree(TEMP_DIR, True)
        raise RuntimeError("Cannot embed 'Roots of Lisp': {0}".format(e))
    
def extractMainContent(soup):
    title_img = findTitleImage(soup)
    title = title_img['alt'].strip()
    main_td = title_img.parent
    
    if INCLUDE_ROOTS_OF_LISP and title == 'The Roots of Lisp':
        embedRootsOfLispArticle(main_td, soup)
    
    main_table = main_td.parent.parent
    while True:
        section = main_table.nextSibling
        if section is None:
            break
        if section.name == 'br':
            main_td.append(section)
        elif section.name != 'table':
            raise RuntimeError("Expected <br> or <table> in main <td>!")
        elif isLinksSection(section):
            rewriteLinksSection(main_td, soup, section)
        elif isEndSection(section) or isAdSection(section) or isDisqusSection(section):
            section.decompose()
        else:
            appendCustomSection(main_td, soup, section)
    
    return main_td.extract()

def retrieveComments(dom, soup):
    comments = soup.find('div', {'id':'__comments'})
    if comments is not None:
        while len(comments.contents) > 0:
            item = comments.contents[0].extract()
            dom.append(item)

def replaceImageWithHeading(img, tag, title, soup):
    hdg = Tag(soup, tag)
    hdg.string = title
    img.replaceWith(hdg)
    
    # Delete the <br>s that follow, up to a maximum of 2
    for _ in xrange(0,2):
        for sib in hdg.nextSiblingGenerator():
            if isinstance(sib, Tag):
                if sib.name != 'br':
                    return
                sib.decompose()
                break
            else:
                if str(sib).strip() != '':
                    return

def replaceTitleImages(dom, soup):
    img = findTitleImage(dom)
    replaceImageWithHeading(img, 'h1', img['alt'], soup)
    
    for img in dom.findAll('img'):
        _, filename = os.path.split(img['src'])
        
        if filename in TITLE_IMAGES:
            replaceImageWithHeading(img, 'h2', TITLE_IMAGES[filename], soup)

def removeBottomAds(dom):
    for table in dom.findAll('table'):
        tbl_text = table.getText('')
        
        if "You'll find this essay and 14 others" in tbl_text:
            while type(table.nextSibling)==type(table) and table.nextSibling.name == 'br':
                table.nextSibling.decompose()
            table.decompose()

def removeScripts(dom):
    for script in dom.findAll('script'):
        script.decompose()

def fixEntities(dom):
    for text_elem in dom.findAll(text=lambda text:not isinstance(text, Comment)):
        text = str(text_elem)
        text = re.sub("&(?!(\\w\\w|#))", '&amp;', text)
        text = re.sub("&(\\w);", "&amp;\\1", text)
        text = text.replace('<', '&lt;').replace('>','&gt;')
        
        text_elem.replaceWith(text)

def addStyle(tag, style):
    if style=='':
        return
    
    sty = tag.get('style').strip() if tag.get('style') is not None else ''
    
    if sty != '' and not sty.endswith(';'):
        sty += ';'
    if not style.strip().endswith(';'):
        style += ';'
    
    tag['style'] = sty + style

def addClass(tag, cls):
    cl = tag.get('class').strip() if tag.get('class') is not None else ''
    tag['class'] = cl + ' ' + cls

def attrToCss(tag, attr, css=None):
    curr_val = tag.get(attr)
    if curr_val is None:
        return
    
    if css is None:
        css = attr+':{0}'
    
    addStyle(tag, css.format(curr_val))
    
    del tag[attr]

def convertFontTags(dom):
    for font in dom.findAll('font'):
        attrToCss(font, 'color')
        del font['face'] # face changes are ignored
        del font['size'] # size changes are ignored
        
        if font.get('style') is not None:
            font.name = 'span'
        else:
            font.replaceWithChildren()

def convertStrikethrough(dom):
    for st in dom.findAll('s'):
        st.name = 'span';
        addStyle(st, 'text-decoration: line-through')

def stripRootUrl(url):
    if url.startswith(ROOT_URL):
        return url[len(ROOT_URL):]
    if url.startswith(ROOT_URL.replace('http://www.','http://')):
        return url[len(ROOT_URL)-4:]
    
    return url

def mustExternalize(link):
    if link in FORCE_EXTERNAL_ARTICLES:
        return True
    if link in MAIN_ARTICLES:
        return False
    if not INCLUDE_APPENDICES:
        return True
    if not INCLUDE_IMAGE_APPENDICES and link in IMAGE_APPENDICES:
        return True
    
    return False

def fixReference(url, bookData):
    link, sep, fragment = url.partition('#')
    
    if link != '':
        link = stripRootUrl(link)

        if not link.startswith(ROOT_URL) and mustExternalize(link):
            link = ROOT_URL + link
        
        if not isExternalUrl(link):
            if link not in bookData.articles:
                bookData.unresolved.add(link)
     
    return link + sep + fragment

def fixAnchors(dom, bookData):
    for link in dom.findAll('a'):
        if REMOVE_DEPRECATED_LINKS:
            if link.get('class') == '_deprecated_link':
                link.replaceWithChildren()
                continue
        
        if link.get('name') is not None:
            link['id'] = link['name']
            del link['name']
        if link.get('hef') is not None:
            if link.get('name') is None:
                link['href'] = link['hef']
            del link['hef']
    
        url = link.get('href')
        if url is not None:
            link['href'] = fixReference(url, bookData)
            addClass(link, '_external_link' if isExternalUrl(link['href']) else '_local_link')

def fixTableStyles(dom):
    for t in dom.findAll(['table','tr','td']):
        attrToCss(t, 'width')
        attrToCss(t, 'bgcolor', 'background-color:{0}')
    
    for cent in dom.findAll('center'):
        for tbl in cent.findAll('table'):
            addStyle(tbl, 'margin: auto')

def fixBrAndHrStyles(dom):
    for br in dom.findAll('br'):
        del br['clear']
    for hr in dom.findAll('hr'):
        del hr['color']
        del hr['height']

def fixImageStyle(img):
    if img.get('alt') is None:
        img['alt'] = ''
    
    attrToCss(img, 'align', 'float:{0}')
    attrToCss(img, 'border')
    attrToCss(img, 'hspace', 'margin-left:{0};margin-right:{0}')
    attrToCss(img, 'vspace', 'margin-top:{0};margin-bottom:{0}')

def resolveImages(dom, bookData):
    for img in dom.findAll('img'):
        filename = img['src'];
        try:
            data = getPage(filename)
        except urllib2.HTTPError:
            filename = 'http://upload.wikimedia.org/wikipedia/commons/c/ce/Transparent.gif'
            data = getPage(filename)
        md5 = hashlib.md5(data).digest()
        
        if md5 in bookData.images:
            img['src'] = bookData.images[md5][1]
        else:
            old_path = cachedPageFilename(filename)
            
            new_path = 'img{0}.{1}'.format(len(bookData.images)+1, imghdr.what(old_path))
            bookData.images[md5] = (old_path, new_path)
        
            img['src'] = new_path
        
        fixImageStyle(img)

def processDom(soup, bookData):
    main_td = extractMainContent(soup)

    retrieveComments(main_td, soup)
    replaceTitleImages(main_td, soup)
    removeBottomAds(main_td)
    removeScripts(main_td)
    convertFontTags(main_td)
    convertStrikethrough(main_td)
    fixEntities(main_td)
    fixAnchors(main_td, bookData)
    fixTableStyles(main_td)
    fixBrAndHrStyles(main_td)
    resolveImages(main_td, bookData)
    
    return main_td

def fixBlockquotes(page):
    page = re.sub('(</?blockquote[^>]*>)', "</p>\\1<p>", page)
    
    return page

def fixCenterTags(page):
    # Compensate for the new line breaks we will introduce
    page = re.sub("</center>\\s*<br />", '</center>', page)
    page = re.sub("<br />\\s*</center>", '</center>', page)
    page = re.sub("<br />\\s*<center>", '<center>', page)
    page = re.sub("<center>\\s*<br />", '<center>', page)
    page = re.sub('</center><center[^>]*>', '<br />', page)
    
    # Replace CENTER tags proper
    page = re.sub('(<center[^>]*>)', '</p><p style="text-align:center">', page)
    page = re.sub('(</center[^>]*>)', '</p><p>', page)
    
    return page

def fixBlockTags(page):
    page = re.sub('(<(hr)\\b[^>]*>)', "</p>\\1<p>", page)
    page = re.sub('(<(pre|ol|ul|table|h\\d)\\b)', "</p>\\1", page)
    page = re.sub('(</(pre|ol|ul|table|h\\d)\\b[^>]*>)', "\\1<p>", page)
    
    return page

def applyFinalCorrections(page):
    page = re.sub('(<(td|li)\\b[^>]*>[^<]*)</p>', "\\1", page)
    page = re.sub('<p>([^<]*</(td|li)\\b)', "\\1", page)
    page = re.sub("<p>\\s*</p>", '', page)

    return page

def addCoda(page):
    return re.sub('(\\s*<br />)*</p>$', '<br /><br /><br /><br /></p><hr />', page)

def postprocessPage(page):
    page = fixBlockquotes(page)
    page = fixCenterTags(page)
    page = fixBlockTags(page)
    page = applyFinalCorrections(page)
    page = addCoda(page)

    return page

def articleFilename(link):
    return link if not isExternalUrl(link) else os.path.split(link)[1]

def renderSection(title, css, content):
    stream = SECTION_TEMPLATE.generate(title=title, css=css, text=genshi.core.Markup(content))
    
    return stream.render('xhtml', doctype='xhtml11', drop_xml_decl=False, strip_whitespace=False)

def loadArticle(bookData, link):
    url = link if isExternalUrl(link) else ROOT_URL + link
    
    page = getPage(url).decode('iso-8859-1')
    
    if '.html' in link:
        title = extractTitle(page)
        page = preprocessPage(page)
        soup = BeautifulSoup(page)
        dom = processDom(soup, bookData)
        content = '<p>{0}</p>'.format(''.join(str(item) for item in dom.contents))
        content = postprocessPage(content)
    else:
        title = guessTitle(page)
        content = '<pre>{0}</pre>'.format(htmlEntities(page))

    bookData.articles[link] = renderSection(title, '', content)
    bookData.unresolved.discard(link)
    
    return title

def getEssayLinks():
    page = getPage(ROOT_URL + 'articles.html')
    soup = BeautifulSoup(page)
    
    return [link['href'] for link in soup.findAll('table', {'width': '455'})[1].findAll('a')]

def getBookData():
    bookData = BookData()
    
    print "Processing essays..."
    
    links = getEssayLinks()
    MAIN_ARTICLES.extend(links)
    for link in links:
        title = loadArticle(bookData, link)
        bookData.main_toc.append((link, title))
    
    if INCLUDE_APPENDICES:
        print "Processing Appendices..."
        
        while len(bookData.unresolved) > 0:
            link = bookData.unresolved.pop()
            title = loadArticle(bookData, link)
            
            if link in IMAGE_APPENDICES:
                bookData.image_toc.append((link, title))
            else:
                bookData.appendix_toc.append((link, title))
    
        bookData.appendix_toc.sort(key=lambda pair:pair[1])
        bookData.image_toc.sort(key=lambda pair:pair[1])
    
    return bookData

def makeBook(bookData, outputFile):
    book = epub.EpubBook()
    book.setTitle(BOOK_TITLE)
    book.setLang('en-US')
    book.addCreator('Paul Graham')
    book.addTitlePage()
    book.addTocPage()
    
    for link, title in bookData.main_toc:
        item = book.addHtml('', articleFilename(link), bookData.articles[link])
        book.addSpineItem(item)
        book.addTocMapNode(item.destPath, title, 1)
    
    for fname, heading, toc in [('_appendices.html', 'Appendices', bookData.appendix_toc),
                                ('_images.html', 'Images', bookData.image_toc)]:
        first = True
        for link, title in toc:
            if first:
                item = book.addHtml('', fname, renderSection(heading, '', '<h1>'+heading+'</h1>'))
                book.addSpineItem(item)
                book.addTocMapNode(item.destPath, heading, 1)
                first = False
            
            item = book.addHtml('', articleFilename(link), bookData.articles[link])
            book.addSpineItem(item)
            book.addTocMapNode(item.destPath, title, 2)
    
    for old_path, new_path  in bookData.images.values():
        book.addImage(old_path, new_path)
    
    outputDir = outputFile+"_files.d"
    if os.path.isdir(outputDir): shutil.rmtree(outputDir)
    book.createBook(outputDir)
    book.createArchive(outputDir, outputFile)
    if not KEEP_OUTPUT_DIR: shutil.rmtree(outputDir)

def checkEPub(outputFile):
    checkers = sorted([f for f in os.listdir('.') if re.match('epubcheck.*[.]jar', f)])
    
    if len(checkers) == 0:
        print "No epubcheck-*.jar found, cannot check book!"
        return
    
    jar = checkers[-1]
    
    subprocess.call(['java', '-jar', jar, outputFile], shell = False)

def main():
    bookData = getBookData()
    
    makeBook(bookData, OUTPUT_FILE)
    
    if CHECK_EPUB:
        checkEPub(OUTPUT_FILE)

main()
