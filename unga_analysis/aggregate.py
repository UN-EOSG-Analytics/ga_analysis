"""Reviewed multilabel aggregation rules; no prior-report imports or model calls."""

def country_theme_value(decisions):
 """decisions: one {value, review_status} per relevant passage for ONE theme."""
 if any(d.get('value')=='Yes' and d.get('review_status')=='reviewed' for d in decisions):return 1
 if decisions and all(d.get('value')=='No' and d.get('review_status')=='reviewed' for d in decisions):return 0
 return None

def classification_complete(passages,codes):
 return bool(passages) and bool(codes) and all(p.get('review_status')=='reviewed' and all(p.get('themes',{}).get(k) in ('Yes','No') for k in codes) for p in passages)

def requests_to_un(records):
 """Reviewed rows where a country asks the UN itself to act; generic cooperation calls are excluded."""
 return [r for r in records if r['review_status']=='reviewed' and r['un_role']=='explicit' and r['stances']['request']]

def yearly_theme_share(n,N,min_N):
 """Percentage only when N meets the protocol threshold; smaller years report counts."""
 return dict(n=n,N=N,pct=round(100*n/N,1) if N and N>=min_N else None,below_threshold=N<min_N)

