"""Country-year OR aggregation with separate review and collection denominators."""
from collections import Counter,defaultdict
from itertools import combinations

from .common import table,save


def coverage_guard(speeches,cfg,allow_partial=False):
    partial=[];coverage={}
    for year in sorted({s['year'] for s in speeches}):
        selected=[s for s in speeches if s['year']==year]
        days=sorted({int(s['origin_file'].split('_day')[1].split('_')[0]) for s in selected if '_day' in s.get('origin_file','')})
        missing_final=year in cfg['scope'].get('partial_years',[]) and not set(range(1,7)).issubset(days)
        if missing_final:partial.append(year)
        coverage[str(year)]=dict(obtained_speeches=len(selected),days_received=days,partial=missing_final,
            participation_roster='not_independently_reconciled',collection_status='partial' if missing_final else 'available_session_records',
            source_types=dict(Counter(s['source_type'] for s in selected)))
    if partial and not allow_partial:
        raise ValueError(f'Final report blocked: incomplete session years {partial}; add Day 6 or explicitly use --allow-partial for a labelled interim report')
    return coverage


def aggregate(speeches,reviews,classified,taxonomy,cfg,out,allow_partial=False):
    coverage=coverage_guard(speeches,cfg,allow_partial)
    by_speech=defaultdict(list);labels=defaultdict(list)
    if len({r['passage_id'] for r in reviews})!=len(reviews):raise ValueError('Duplicate reviewed passage')
    expected={p['passage_id'] for s in speeches for p in s['passages']}
    if {r['passage_id'] for r in reviews}!=expected:raise ValueError('Cannot aggregate: incomplete passage review coverage')
    positives={r['passage_id'] for r in reviews if r['ai_status']=='Yes'}
    if {r['passage_id'] for r in classified}!=positives or len(classified)!=len(positives):raise ValueError('Classification must cover each verified AI passage exactly once')
    for r in reviews:by_speech[r['speech_id']].append(r)
    for r in classified:labels[r['speech_id']].append(r)
    codes=taxonomy['codes'];matrix=[];evidence=[];institutions=[];keywords=[]
    for s in speeches:
        rr=by_speech[s['speech_id']];cc=labels[s['speech_id']]
        ai='Yes' if any(r['ai_status']=='Yes' for r in rr) else 'No' if all(r['ai_status']=='No' for r in rr) else 'Uncertain'
        source_pending=(s.get('source_review_notes') or {}).get('status')=='pending_delivery_verification'
        if source_pending and ai=='No':ai='Uncertain'
        review_complete=all(r['ai_status']!='Uncertain' for r in rr) and not source_pending
        complete=ai=='Yes' and review_complete and all(r['classification_complete'] for r in cc)
        keyword_complete=ai=='Yes' and review_complete and all(r['keyword_review_complete'] for r in cc)
        values={}
        for code in codes:
            values[code]=1 if any(r['themes'][code]=='Yes' for r in cc) else 0 if complete or (ai=='No' and review_complete) else None
        matrix.append(dict(speech_id=s['speech_id'],year=s['year'],country_iso3=s['country_iso3'],region=s['analytical_group'],
            ai_status=ai,ai_review_complete=review_complete,theme_review_complete=complete,keyword_review_complete=keyword_complete,
            source_type=s['source_type'],text_accuracy=s.get('text_accuracy'),partial_year=coverage[str(s['year'])]['partial'],**values))
    for i,r in enumerate(classified,1):
        eid=f'E{i:05d}'
        base=dict(evidence_id=eid,passage_id=r['passage_id'],speech_id=r['speech_id'],year=r['year'],iso3=r['country_iso3'],region=r['region'],
                  source_file=r['source_file'],source_sha256=r['source_sha256'],origin_file=r['origin_file'],locator=r['locator'],
                  quote=r['reviews'][0]['quote'],review_status=r['review_status'],human_reviewed=False)
        evidence.append(dict(base,ai_status='Yes',themes=r['themes'],theme_evidence=r['evidence'],institutions=r['institutions'],source_review_notes=r.get('source_review_notes')))
        for institution in r['institutions']:
            institutions.append(dict(base,**{k:v for k,v in institution.items() if k not in base},quote=institution['quote'],review_status=institution['review_status']))
        for word in r['keywords']:
            keywords.append(dict(base,normalized_term=word['normalized_term'],original_term=word['original_term'],quote=word['quote'],review_status=word['review_status'],language='en'))
    annual=[];regional=[];prevalence=[];cooccurrence=[];keyword_trends=[];stance_counts=[]
    for year in sorted({s['year'] for s in speeches}):
        rr=[r for r in matrix if r['year']==year]
        def ai_counts(group):
            n=sum(r['ai_status']=='Yes' for r in group);N=sum(r['ai_status'] in ('Yes','No') for r in group)
            return dict(n=n,N=N,pct=100*n/N if N else None,obtained=len(group),uncertain=len(group)-N,partial=coverage[str(year)]['partial'])
        annual.append(dict(year=year,**ai_counts(rr)))
        for region in sorted({s['analytical_group'] for s in speeches}):
            regional.append(dict(year=year,region=region,**ai_counts([r for r in rr if r['region']==region])))
        eligible=[r for r in rr if r['theme_review_complete']];N=len(eligible)
        counts={code:sum(r[code]==1 for r in eligible) for code in codes}
        for code in codes:
            prevalence.append(dict(year=year,code=code,theme=codes[code]['label'],n=counts[code],N=N,
                pct=100*counts[code]/N if N>=cfg['themes']['min_N_for_yearly_percentages'] else None,
                below_threshold=N<cfg['themes']['min_N_for_yearly_percentages'],partial=coverage[str(year)]['partial'],
                countries=[r['country_iso3'] for r in eligible if r[code]==1]))
        for a,b in combinations(codes,2):
            both=sum(r[a]==1 and r[b]==1 for r in eligible)
            cooccurrence.append(dict(year=year,theme_a=a,theme_b=b,n_both=both,n_a=counts[a],n_b=counts[b],N=N,
                p_b_given_a=both/counts[a] if counts[a] else None,p_a_given_b=both/counts[b] if counts[b] else None,
                baseline_a=counts[a]/N if N else None,baseline_b=counts[b]/N if N else None,partial=coverage[str(year)]['partial']))
        word_eligible={r['speech_id'] for r in rr if r['keyword_review_complete']}
        words=defaultdict(set)
        for w in keywords:
            if w['year']==year and w['review_status']=='reviewed' and w['speech_id'] in word_eligible:words[w['normalized_term']].add(w['iso3'])
        for term,countries in words.items():
            earlier=[w['year'] for w in keywords if w['normalized_term']==term and w['review_status']=='reviewed']
            keyword_trends.append(dict(year=year,term=term,n=len(countries),N=len(word_eligible),countries=sorted(countries),
                pct=100*len(countries)/len(word_eligible) if word_eligible else None,
                first_observed_year=min(earlier),recurring=len(countries)>=2,partial=coverage[str(year)]['partial'],
                caveat='First observed in available corpus; source and collection differences remain.'))
        for mechanism in cfg['institutions']['mechanisms']:
            for stance in cfg['institutions']['stances']:
                members={r['iso3'] for r in institutions if r['year']==year and r['mechanism']==mechanism and r['review_status']=='reviewed' and r['stances'][stance] and (stance!='request' or r['un_role']=='explicit')}
                if members:stance_counts.append(dict(year=year,mechanism=mechanism,stance=stance,n=len(members),countries=sorted(members),partial=coverage[str(year)]['partial']))
    matched=[]
    for row in keyword_trends:
        recurring_years=[w['year'] for w in keyword_trends if w['term']==row['term'] and w['recurring']]
        row['first_recurring_year']=min(recurring_years) if recurring_years else None
    years=sorted({r['year'] for r in matrix})
    for first,second in zip(years,years[1:]):
        a={r['country_iso3']:r for r in matrix if r['year']==first and r['theme_review_complete']}
        b={r['country_iso3']:r for r in matrix if r['year']==second and r['theme_review_complete']}
        common=set(a)&set(b)
        for code in codes:
            matched.append(dict(year_from=first,year_to=second,code=code,N=len(common),
                n_from=sum(a[c][code]==1 for c in common),n_to=sum(b[c][code]==1 for c in common),
                countries=sorted(common),partial=coverage[str(second)]['partial']))
    files={'country_year_theme_matrix':matrix,'evidence_register':evidence,'institution_stances':institutions,
           'keyword_evidence_register':keywords,'yearly_keyword_trends':keyword_trends,'annual_mentions':annual,
           'regional_mentions':regional,'theme_prevalence':prevalence,'theme_cooccurrence':cooccurrence,
           'institution_stance_counts':stance_counts,'matched_panel_trends':matched}
    for name,rows in files.items():table(out/(name+'.csv'),rows)
    summary=dict(coverage=coverage,annual=annual,regional=regional,theme_prevalence=prevalence,cooccurrence=cooccurrence,
                 institution_stance_counts=stance_counts,keywords=keyword_trends,matched_panel=matched,
                 unresolved_ai_speeches=sum(r['ai_status']=='Uncertain' for r in matrix),
                 incomplete_theme_speeches=sum(r['ai_status']=='Yes' and not r['theme_review_complete'] for r in matrix),
                 review_method='two automated source-grounded reviews; no claim of human verification',human_reviewed=False)
    save(out/'aggregates.json',summary)
    return summary,evidence,institutions,matrix
