"""Kalkylark utan beroenden.

Skriver .xlsx för hand (en xlsx är en zip med XML) så att appen inte behöver
openpyxl eller LibreOffice. Arkivet får ett rubrikblock överst med skola,
program och ansvarig lärare, eftersom arket ska skickas till den som ska
fylla i det — inte bara läsas av oss.

CSV skrivs med semikolon, annars lägger svensk Excel allt i en kolumn.
"""
import csv
import io
import os
import re
import time
import zipfile

# (nyckel, rubrik, typ)  typ "tal" blir ett riktigt tal i arket så att
# kolumnen går att summera och sortera i Excel.
KOLUMNER = [
    ("namn", "Benämning", "text"),
    ("kategori", "Kategori", "text"),
    ("antal", "Antal", "tal"),
    ("enhet", "Enhet", "text"),
    ("dimension", "Dimension / art.nr", "text"),
    ("tillverkare", "Tillverkare", "text"),
    ("inkopsar", "Inköpsår", "text"),
    ("skick", "Skick", "text"),
    ("investeringsbehov", "Investeringsbehov", "text"),
    ("prioritet", "Prioritet", "text"),
    ("pris", "Pris/enhet", "tal"),
    ("summa", "Summa", "tal"),
    ("placering", "Placering", "text"),
    ("program", "Program", "text"),
    ("anteckning", "Anteckning", "text"),
    ("bild", "Bild", "text"),
    ("andrad", "Ändrad", "text"),
]

BEHOV = {"behall": "Behåll", "investera": "Investera", "avveckla": "Avveckla",
         "vetej": "Vet ej"}
PRIORITET = {"hog": "Hög", "medel": "Medel", "lag": "Låg"}


def _cell(v):
    if v is None:
        return ""
    s = str(v)
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    return s.strip()


def _xml_escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def _kolnamn(i):
    namn = ""
    i += 1
    while i:
        i, rest = divmod(i - 1, 26)
        namn = chr(65 + rest) + namn
    return namn


def _behov_text(p):
    return BEHOV.get(_cell(p.get("investeringsbehov")), _cell(p.get("investeringsbehov")))


def _prio_text(p):
    return PRIORITET.get(_cell(p.get("prioritet")), _cell(p.get("prioritet")))


def _varde(p, nyckel):
    if nyckel == "summa":
        try:
            return round(float(p.get("antal") or 0) * float(p.get("pris") or 0), 2)
        except (TypeError, ValueError):
            return ""
    if nyckel == "investeringsbehov":
        return _behov_text(p)
    if nyckel == "prioritet":
        return _prio_text(p)
    return _cell(p.get(nyckel))


def rubrikblock(meta):
    """Raden överst i arket. meta = skola, program, ansvarig, deadline."""
    rader = [["Inventering av utrustning — VVS"]]
    if meta.get("skola"):
        rader.append(["Skola:", _cell(meta["skola"])])
    if meta.get("program"):
        rader.append(["Program:", _cell(meta["program"])])
    if meta.get("ansvarig"):
        rader.append(["Ansvarig lärare:", _cell(meta["ansvarig"])])
    if meta.get("deadline"):
        rader.append(["Fylls i senast:", _cell(meta["deadline"])])
    rader.append(["Utskrivet:", time.strftime("%Y-%m-%d %H:%M")])
    rader.append([])
    return rader


def rader(poster, meta=None):
    """-> (rubrikblock, rubrikrad, datarader, summeringsblock)"""
    def nyckel(p):
        return (_cell(p.get("kategori")).lower(), _cell(p.get("namn")).lower())

    sorterade = sorted(poster, key=nyckel)
    data = [["#"] + [rubrik for _, rubrik, _ in KOLUMNER]]
    for n, p in enumerate(sorterade, 1):
        data.append([str(n)] + [_cell(_varde(p, k)) for k, _, _ in KOLUMNER])

    # summering: vad kostar det att investera, och hur mycket är uttjänt
    summor = {}
    for p in sorterade:
        summa = 0.0
        try:
            summa = float(p.get("antal") or 0) * float(p.get("pris") or 0)
        except (TypeError, ValueError):
            pass
        b = _behov_text(p) or "Ej ifyllt"
        s = summor.setdefault(b, {"poster": 0, "antal": 0.0, "pris": 0.0})
        s["poster"] += 1
        try:
            s["antal"] += float(p.get("antal") or 0)
        except (TypeError, ValueError):
            pass
        s["pris"] += summa
    slut = [[], ["Sammanställning"]]
    slut.append(["Investeringsbehov", "Poster", "Antal", "Summa kr"])
    for b, s in sorted(summor.items(), key=lambda x: -x[1]["pris"]):
        slut.append([b, s["poster"], round(s["antal"], 1), round(s["pris"], 2)])
    totalt = round(sum(s["pris"] for s in summor.values()), 2)
    slut.append(["Totalt uppskattat", len(sorterade),
                 round(sum(s["antal"] for s in summor.values()), 1), totalt])
    return rubrikblock(meta or {}), data[0], data[1:], slut


def csv_bytes(poster, meta=None):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    block, rubrik, data, slut = rader(poster, meta)
    for rad in block:
        w.writerow(rad)
    w.writerow(rubrik)
    for rad in data:
        w.writerow(rad)
    for rad in slut:
        w.writerow(rad)
    return buf.getvalue().encode("utf-8-sig")


def xlsx_bytes(poster, meta=None, titel="Inventering"):
    block, rubrik, data, slut = rader(poster, meta)
    alla = block + [rubrik] + data + slut
    rubrikrad = len(block) + 1                 # 1-baserad rad för rubriken
    kol = len(rubrik)
    tal_kol = {i for i, (_, _, t) in enumerate([(None, None, "text")] + KOLUMNER)
               if t == "tal"}

    sheet = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             '<worksheet xmlns="http://schemas.openxmlformats.org/'
             'spreadsheetml/2006/main">',
             '<sheetViews><sheetView workbookViewId="0">',
             f'<pane ySplit="{rubrikrad}" topLeftCell="A{rubrikrad+1}" '
             'activePane="bottomLeft" state="frozen"/>',
             '</sheetView></sheetViews>',
             '<sheetFormatPr defaultRowHeight="15"/><cols>']
    bredder = [5, 34, 14, 8, 7, 22, 16, 8, 12, 17, 13, 11, 10, 20, 14, 26, 14, 13]
    for i, b in enumerate(bredder[:kol]):
        sheet.append(f'<col min="{i+1}" max="{i+1}" width="{b}" customWidth="1"/>')
    sheet.append("</cols><sheetData>")

    for r, rad in enumerate(alla, 1):
        fet = (r == rubrikrad)
        sheet.append(f'<row r="{r}">')
        for c, val in enumerate(rad):
            s = _cell(val)
            if s == "":
                continue
            ref = f"{_kolnamn(c)}{r}"
            stil = ' s="2"' if fet else (' s="1"' if r == 1 else "")
            if c in tal_kol:                     # riktigt tal
                try:
                    tal = float(s.replace(",", "."))
                    sheet.append(f'<c r="{ref}"{stil}><v>{tal:g}</v></c>')
                    continue
                except ValueError:
                    pass
            sheet.append(f'<c r="{ref}" t="inlineStr"{stil}><is>'
                         f'<t xml:space="preserve">{_xml_escape(s)}</t></is></c>')
        sheet.append("</row>")
    sheet.append("</sheetData>")
    sheet.append(f'<autoFilter ref="A{rubrikrad}:{_kolnamn(kol-1)}{rubrikrad+len(data)}"/>')
    sheet.append("</worksheet>")
    sheet_xml = "".join(sheet)

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>')
    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f'<sheets><sheet name="{_xml_escape(titel[:28])}" sheetId="1" r:id="rId1"/></sheets>'
                '</workbook>')
    wb_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
               '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
               '</Relationships>')
    # tre stilar: vanlig, fet (rubrik), stor fet (arkets titel)
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="3">'
              '<font><sz val="11"/><name val="Calibri"/></font>'
              '<font><b/><sz val="11"/><name val="Calibri"/></font>'
              '<font><b/><sz val="14"/><name val="Calibri"/></font></fonts>'
              '<fills count="2"><fill><patternFill patternType="none"/></fill>'
              '<fill><patternFill patternType="gray125"/></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="3">'
              '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
              '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
              '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
              '</cellXfs></styleSheet>')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/styles.xml", styles)
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buf.getvalue()


def skriv(poster, mapp, meta=None, basnamn=None):
    basnamn = basnamn or time.strftime("inventering-%Y-%m-%d")
    os.makedirs(mapp, exist_ok=True)
    xs = os.path.join(mapp, basnamn + ".xlsx")
    cs = os.path.join(mapp, basnamn + ".csv")
    with open(xs, "wb") as fh:
        fh.write(xlsx_bytes(poster, meta))
    with open(cs, "wb") as fh:
        fh.write(csv_bytes(poster, meta))
    return xs, cs
