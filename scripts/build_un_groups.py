"""Freeze the official UN regional-group roster with explicit single-count rules."""
import csv,json,hashlib,sys,re
from pathlib import Path
from collections import Counter,defaultdict
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'.deps'))
from lxml import html
import country_converter as coco
source=ROOT/'output/primary_sources/UN_regional_groups.html'
tree=html.fromstring(source.read_bytes());cc=coco.CountryConverter()
names=['African States','Asia-Pacific States','Eastern European States','Latin American and Caribbean States','Western European and other States']
members=defaultdict(set);un_names={}
for group in names:
 h=next(h for h in tree.xpath('//h2') if h.text_content().strip()==group)
 tables=h.xpath('ancestor::table[1]')
 table=tables[0] if tables else h.xpath('following::table[1]')[0]
 for cell in table.xpath('.//td'):
  label=re.sub(r'\s+',' ',cell.text_content()).strip().rstrip('*').strip()
  if not label:continue
  iso=cc.convert({'Naoero':'Nauru','Bahamas (The)':'Bahamas'}.get(label,label),to='ISO3',not_found='UNKNOWN')
  if iso=='UNKNOWN':raise ValueError((group,label))
  members[iso].add(group);un_names[iso]=label
canonical=set(cc.data.loc[cc.data.UNmember.notna(),'ISO3'])
assert set(members)==canonical,(canonical-set(members),set(members)-canonical)
rows=[]
for iso in sorted(members):
 groups=sorted(members[iso]);note='Single formal group in the current DGACM roster.';status='formal_member'
 if iso=='USA':
  assigned='Not a formal member of any regional group';status='WEOG_observer_electoral_association'
  note='DGACM says no formal group membership; attends WEOG as observer and is considered WEOG for elections. Kept separate here because this is speech analysis, not an election.'
 elif iso=='TUR':
  assigned='Western European and other States';status='dual_participation_single_electoral_allocation'
  note='Full participation in Asia-Pacific and WEOG; assigned once to WEOG using the explicit UN electoral convention.'
 else:
  assert len(groups)==1,(iso,groups);assigned=groups[0]
  if iso=='KIR':note='The current DGACM roster explicitly lists Kiribati in Asia-Pacific. Older documents describing nonmembership are not used. This fixed mapping is not a historical-membership reconstruction.'
  if iso=='ISR':note='DGACM records WEOG membership and its permanent renewal in 2004.'
 rows.append(dict(iso3=iso,country=un_names[iso],official_listed_groups=';'.join(groups),analytical_group=assigned,membership_status=status,assignment_note=note,mapping_as_of='2026-09-25',date_timezone='America/New_York',applied_years='2017-2026 fixed analytical mapping',source_url='https://www.un.org/dgacm/en/node/3935',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
out=ROOT/'config';out.mkdir(exist_ok=True)
with (out/'un_regional_groups.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
print(json.dumps(dict(countries=len(rows),groups=dict(Counter(r['analytical_group'] for r in rows))),indent=2))
