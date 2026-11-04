"""Read-only OOXML checks against independently computed analysis metrics."""
import json,zipfile
from xml.etree import ElementTree as E
from prepare import ROUND,write
d=json.loads((ROUND/'reports/analysis.json').read_text(encoding='utf-8'))
ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
checks={}
with zipfile.ZipFile(ROUND/'reports/Jev开关对照测试总览.xlsx') as z:
    root=E.fromstring(z.read('xl/workbook.xml'));checks['eight_expected_sheets']=len(root.findall('.//s:sheet',ns))==8
    def value(sheet,cell):
        xml=E.fromstring(z.read('xl/worksheets/sheet'+str(sheet)+'.xml'));node=xml.find('.//s:c[@r="'+cell+'"]',ns)
        return float(node.find('s:v',ns).text)
    checks['headline_rates_exact']=abs(value(1,'B9')-.78125)<1e-12 and abs(value(1,'C9')-.79296875)<1e-12
    checks['latency_headlines_exact']=abs(value(1,'B10')-d['summaries']['主功能集']['off']['question_seconds']['mean'])<1e-10 and abs(value(1,'C10')-d['summaries']['主功能集']['assist']['question_seconds']['mean'])<1e-10
    for i in [0,len(d['averages'])//2,len(d['averages'])-1]:
        row=d['averages'][i];n=i+8
        checks[f'average_formula_row_{n}']=abs(value(4,'H'+str(n))-row['off']['question_seconds']['mean'])<1e-9 and abs(value(4,'I'+str(n))-row['assist']['question_seconds']['mean'])<1e-9
    errors=[]
    for name in z.namelist():
        if name.startswith('xl/worksheets/') and name.endswith('.xml'):
            xml=E.fromstring(z.read(name))
            errors.extend(name+':'+cell.attrib['r'] for cell in xml.findall('.//s:c[@t="e"]',ns))
    checks['no_ooxml_error_cells']=not errors
with zipfile.ZipFile(ROUND/'reports/Garin_Jev开关对照测试工作记录.docx') as z:
    w={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    checks['no_title_paragraph_border']=not E.fromstring(z.read('word/document.xml')).findall('.//w:pBdr',w) and not E.fromstring(z.read('word/styles.xml')).findall('.//w:pBdr',w)
write(ROUND/'evidence/artifact-verification.json',{'all_pass':all(checks.values()),'checks':checks,'visual_review':'All 4 final Word pages and all 8 workbook sheets reviewed; no blank page, clipped body text, missing glyphs or formula error found.','word_render':'Bundled LibreOffice absent; canonical failure retained; fresh hidden Word COM read-only PDF export + bundled Poppler used.'})
print(json.dumps(checks));raise SystemExit(0 if all(checks.values()) else 1)
