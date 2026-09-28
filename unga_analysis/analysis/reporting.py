"""Grounded report drafting and shared four-page Word/PDF publication layout."""
from pathlib import Path
from xml.sax.saxutils import escape
import re
import os
import subprocess

from .common import obj,arr,STR,BOOL,SYSTEM,ask,save,table,now

TITLES=['Key Facts and Figures','Themes','Role of UN','Implications']
PARAGRAPH=obj(text=STR,evidence_ids=arr(STR),reference_ids=arr(STR),metric_keys=arr(STR))
REPORT=obj(sections=arr(obj(title={'type':'string','enum':TITLES},paragraphs=arr(PARAGRAPH))),
           recommendations=arr(obj(addressee=STR,action=STR,rationale=STR,evidence_ids=arr(STR),metric_keys=arr(STR))))


def metric_register(stats):
    metrics={}
    for name in ('annual','regional','theme_prevalence','cooccurrence','institution_stance_counts','keywords','matched_panel'):
        for i,row in enumerate(stats[name],1):metrics[f'{name}:{i}']=row
    return metrics


def draft_report(stats,evidence,institutions,taxonomy,reference_facts,provider,out):
    metrics=metric_register(stats)
    source={r['evidence_id']:r for r in evidence}
    refs={r['reference_id'] for r in reference_facts}
    # Bound narrative input while all numeric tables and classifications remain exported.
    year=max(int(y) for y in stats['coverage'])
    latest=[r for r in evidence if r['year']==year]
    historical=[r for r in evidence if r['year']!=year]
    selected=[]
    for code in taxonomy['codes']:
        selected.extend([r for r in latest if r['themes'].get(code)=='Yes'][:4])
        selected.extend([r for r in historical if r['themes'].get(code)=='Yes'][:2])
    selected.extend(latest[:12])
    institutional_ids={r['evidence_id'] for r in institutions}
    selected.extend(r for r in evidence if r['evidence_id'] in institutional_ids and r['year']==year)
    selected=list({r['evidence_id']:r for r in selected}.values())
    selected=selected[:160]
    prompt_metrics={k:v for k,v in metrics.items() if k.startswith('annual:') or
        (k.startswith(('regional:','theme_prevalence:','institution_stance_counts:')) and v['year']==year)}
    for name in ('cooccurrence','keywords','matched_panel'):
        relevant=[(k,v) for k,v in metrics.items() if k.startswith(name+':') and (v.get('year')==year or v.get('year_to')==year)]
        relevant.sort(key=lambda kv:kv[1].get('n_both',kv[1].get('n',0)),reverse=True)
        prompt_metrics.update(relevant[:12])
    selected_ids={r['evidence_id'] for r in selected}
    payload=dict(report_year=year,coverage=stats['coverage'],metrics=prompt_metrics,taxonomy=taxonomy,
                 speech_evidence=[{k:r[k] for k in ('evidence_id','year','iso3','quote','themes','theme_evidence','review_status')} for r in selected],
                 institutions=[{k:r[k] for k in ('evidence_id','year','iso3','mechanism','stances','requested_functions','quote','review_status')} for r in institutions if r['evidence_id'] in selected_ids],
                 background=reference_facts,
                 review_method=stats['review_method'],unresolved_ai_speeches=stats['unresolved_ai_speeches'],
                 incomplete_theme_speeches=stats['incomplete_theme_speeches'])
    def validate(value):
        if [s['title'] for s in value['sections']]!=TITLES:raise ValueError('Exactly four ordered report sections required')
        for section in value['sections']:
            if not 1<=len(section['paragraphs'])<=2:raise ValueError('Use one or two concise paragraphs per section')
            for p in section['paragraphs']:
                if len(p['text'].split())>90:raise ValueError('Report paragraphs must be at most 90 words')
                if not (p['evidence_ids'] or p['reference_ids'] or p['metric_keys']):raise ValueError('Each analytical claim needs source or metric references')
                if set(p['evidence_ids'])-selected_ids or set(p['reference_ids'])-refs or set(p['metric_keys'])-set(prompt_metrics):
                    raise ValueError('Unknown report citation')
        if not 3<=len(value['recommendations'])<=5:raise ValueError('Need 3-5 concise recommendations')
        for r in value['recommendations']:
            if len((r['action']+' '+r['rationale']).split())>65:raise ValueError('Recommendation too long')
            if not (r['evidence_ids'] or r['metric_keys']) or set(r['evidence_ids'])-selected_ids or set(r['metric_keys'])-set(prompt_metrics):raise ValueError('Recommendation needs valid supplied speech or metric evidence')
    instructions=SYSTEM+('Draft an English UN EOSG/SPMU strategic report for the latest year, with the four exact sections in order. '
        'Use one or two paragraphs of at most 90 words per section and 3-5 recommendations of at most 65 words each, '
        'naming UN/SPMU, Tech Envoy, Panel or Dialogue as addressees. Numbers are already supplied and must not be recomputed or invented. '
        'Tables/charts will be inserted separately. Cite provided evidence IDs, metric keys and background reference IDs. '
        'Distinguish institutional background, Member State positions and your analytical proposals. '
        'Do not imply endorsement, causation, alignment, treaty mandates or completed commitments without evidence. '
        'Treat theme percentages with N<20 as unavailable; discuss counts instead. Partial years are interim, not completed annual trends. '
        'Account for automated-review limits and official-versus-ASR changes. Preserve any disagreement or draft status in background sources. '
        'Do not claim current institutional status from undated or draft documents. No rhetorical filler.')
    report=ask(provider,'report_draft',payload,REPORT,instructions,validate,max_tokens=7000)
    # Check factual narrative against the actual source register; allow a corrected full report.
    report=ask(provider,'report_fact_check',dict(payload,draft=report),REPORT,SYSTEM+
        'Audit and correct every claim, number, attribution, institutional status and recommendation in the draft. '
        'Use only the supplied tables and source quotes. Remove unsupported assertions. Keep exactly the specified four sections, '
        'one or two <=90-word paragraphs per section, and 3-5 <=65-word recommendations, with existing citations. '
        'Do not label these two automated passes as human verification.',validate,max_tokens=7000)
    save(out/'report_content.json',report)
    save(out/'report_metrics.json',metrics)
    return report


def charts(stats,destination):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    year=max(int(y) for y in stats['coverage'])
    rows=stats['annual']
    fig,ax=plt.subplots(figsize=(7.2,2.35),layout='constrained')
    ax.plot([r['year'] for r in rows],[r['pct'] if r['pct'] is not None else float('nan') for r in rows],color='#174b68',marker='o')
    for r in rows:
        if r['partial'] and r['pct'] is not None:ax.scatter(r['year'],r['pct'],marker='s',s=90,facecolors='white',edgecolors='#ae5c21',zorder=3)
    ax.set(xlabel='General Debate year',ylabel='AI mention share (%)',ylim=(0,100),xticks=[r['year'] for r in rows])
    ax.grid(axis='y',alpha=.2);ax.spines[['top','right']].set_visible(False)
    trend=destination/'annual_trend.png';fig.savefig(trend,dpi=180);plt.close(fig)
    themes=sorted([r for r in stats['theme_prevalence'] if r['year']==year],key=lambda r:r['n'],reverse=True)[:8]
    fig,ax=plt.subplots(figsize=(7.2,2.7),layout='constrained')
    percent=bool(themes and themes[0]['pct'] is not None)
    if themes:
        ax.barh([r['theme'] for r in themes][::-1],[r['pct'] if percent else r['n'] for r in themes][::-1],color='#247e87')
    else:ax.text(.5,.5,'No fully classified AI-positive speeches',ha='center',va='center',transform=ax.transAxes)
    ax.set_xlabel('Share of fully classified AI-positive countries (%)' if percent else 'Country count (N below percentage threshold)')
    ax.spines[['top','right']].set_visible(False)
    theme=destination/'theme_prevalence.png';fig.savefig(theme,dpi=180);plt.close(fig)
    return trend,theme


def pages(report,stats,institutions,reference_facts,reference_inventory,figures):
    year=max(int(y) for y in stats['coverage']);current=next(r for r in stats['annual'] if r['year']==year)
    partial=current['partial'];sections={s['title']:s for s in report['sections']}
    def prose(title):
        values=[]
        for p in sections[title]['paragraphs']:
            cites=p['evidence_ids']+p['reference_ids']+p['metric_keys']
            values.append(('paragraph',p['text']+' ['+'; '.join(cites)+']'))
        return values
    def ratio(row):return f"{row['n']}/{row['N']} ({row['pct']:.1f}%)" if row['pct'] is not None else f"{row['n']}/{row['N']} (NA)"
    first=[('title',TITLES[0]),('paragraph',f"UNGA{year-1945} | {'INTERIM - partial session' if partial else 'Available session records'} | Analysis date {now()[:10]}. "
        f"AI mentions: {ratio(current)} reviewed Member State addresses; {current['obtained']} obtained and {current['uncertain']} unresolved. "
        'Unobserved country-years are not counted as negatives.'),('image',str(figures[0]))]
    rows=[['UN regional group','AI mentions n/N','Uncertain']]
    for r in stats['regional']:
        if r['year']==year:rows.append([r['region'],ratio(r),str(r['uncertain'])])
    first.append(('table',rows));first+=prose(TITLES[0])
    first.append(('small','Source changes: official English records (2017-2024); user-accepted automatic transcripts (2025-2026). Squares mark partial years. Regional mapping fixed at 25 September 2026.'))
    second=[('title',TITLES[1]),('image',str(figures[1]))]+prose(TITLES[1])
    top=sorted([r for r in stats['cooccurrence'] if r['year']==year and r['n_both']],key=lambda r:r['n_both'],reverse=True)[:2]
    if top:second.append(('table',[['Theme pair','Joint n / N','P(B|A) / P(A|B)']]+[[r['theme_a']+' + '+r['theme_b'],f"{r['n_both']} / {r['N']}",f"{r['p_b_given_a']:.2f} / {r['p_a_given_b']:.2f}"] for r in top]))
    terms=sorted([r for r in stats['keywords'] if r['year']==year],key=lambda r:r['n'],reverse=True)[:4]
    if terms:second.append(('table',[['Reviewed expression','Countries n/N','First observed']]+[[r['term'],f"{r['n']}/{r['N']}",str(r['first_observed_year'])] for r in terms]))
    second.append(('small','Theme denominator: AI-positive countries with completed thematic review. Multiple labels may sum above 100%. Co-mention is within the same country-year, not evidence of alignment or a sentence-level link. Full tables include baselines and matched-country comparisons.'))
    third=[('title',TITLES[2])]+prose(TITLES[2])
    stances=[r for r in stats['institution_stance_counts'] if r['year']==year]
    if stances:third.append(('table',[['Mechanism / stance','n','Countries']]+[[r['mechanism']+' / '+r['stance'],str(r['n']),', '.join(r['countries'][:10])+(f" +{len(r['countries'])-10} (see CSV)" if len(r['countries'])>10 else '')] for r in stances[:9]]))
    models=[r for r in institutions if r['year']==year and r['review_status']=='reviewed' and ('-like' in r['mechanism'] or r['mechanism'].startswith('New body'))]
    if models:third.append(('table',[['Model / proposer','Requested function','Evidence']]+[[r['mechanism']+' / '+r['iso3'],', '.join(r['requested_functions']),r['evidence_id']+': '+ ' '.join(r['quote'].split()[:25])+(' …' if len(r['quote'].split())>25 else '')] for r in models[:4]]))
    third.append(('small','Mention, welcome, support, request and commitment are separate. Only explicit UN requests enter UN-request counts. Country positions derive from speech evidence; background proposals and drafts do not enter those counts. Full stance and model tables accompany this report.'))
    fourth=[('title',TITLES[3])]+prose(TITLES[3])
    for r in report['recommendations']:
        fourth.append(('paragraph',r['addressee']+': '+r['action']+' '+r['rationale']+' ['+'; '.join(r['evidence_ids']+r['metric_keys'])+']'))
    fourth.append(('small',f"Review limits: two automated text/classification passes with exact-quote checks; no full audio or human verification. "
        f"Unresolved AI speeches: {stats['unresolved_ai_speeches']}; incomplete thematic cases: {stats['incomplete_theme_speeches']}. "
        'The 2025 VCT prepared-only paragraph remains unresolved if its source note persists. Participation rosters are not independently reconciled. Recommendations are analytical proposals.'))
    used={r for s in report['sections'] for p in s['paragraphs'] for r in p['reference_ids']}
    if used:
        fourth.append(('small','Background locators: '+', '.join(sorted(used))+'. See reference_context.json and reference_inventory.json for source, page/paragraph, status and retrieval date.'))
    if any(r.get('status')=='not_verified_at_run' for r in reference_inventory):
        fourth.append(('small','Some official UN web pages could not be retrieved at this run; current institutional status is not fully verified. Draft/background statements are dated and qualified accordingly.'))
    return [first,second,third,fourth]


def render(report_pages,destination,basename,use_word=True):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph,Table,TableStyle,Image,Spacer
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from docx import Document
    from docx.shared import Inches,Pt
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    font='Helvetica';bold='Helvetica-Bold'
    windows=Path('C:/Windows/Fonts')
    if (windows/'arial.ttf').exists():
        pdfmetrics.registerFont(TTFont('ReportArial',str(windows/'arial.ttf')))
        pdfmetrics.registerFont(TTFont('ReportArialBold',str(windows/'arialbd.ttf')))
        font='ReportArial';bold='ReportArialBold'
    width,height=A4;content_width=width-88;available=height-92
    prepared=[];sizes=[]
    for page in report_pages:
        for size in (10,9.5,9,8.5):
            styles={kind:ParagraphStyle(kind,fontName=bold if kind=='title' else font,
                fontSize=17 if kind=='title' else size-1 if kind=='small' else size,
                leading=21 if kind=='title' else (size-1 if kind=='small' else size)*1.3,
                textColor=colors.HexColor('#163e54') if kind=='title' else colors.HexColor('#263443')) for kind in ('title','paragraph','small')}
            flows=[]
            for kind,value in page:
                if kind=='image':
                    img=Image(value,width=content_width,height=content_width*(2.35/7.2 if 'annual' in value else 2.7/7.2));flows.append(img)
                elif kind=='table':
                    cells=[[Paragraph(escape(str(c)),styles['small']) for c in row] for row in value]
                    widths=[content_width*.46,content_width*.24,content_width*.30] if len(value[0])==3 else [content_width/len(value[0])]*len(value[0])
                    t=Table(cells,colWidths=widths)
                    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e4edf1')),('VALIGN',(0,0),(-1,-1),'TOP'),
                        ('LINEBELOW',(0,0),(-1,0),.5,colors.HexColor('#aac0cb')),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]));flows.append(t)
                else:flows.append(Paragraph(escape(value),styles[kind]))
                flows.append(Spacer(1,7))
            total=sum(f.wrap(content_width,available)[1] for f in flows)
            if total<=available:break
        else:raise ValueError('Report page exceeds layout bounds; shorten prose/table content before publication')
        prepared.append(flows);sizes.append(size)
    pdf=destination/(basename+'.pdf');canvas=Canvas(str(pdf),pagesize=A4)
    canvas.setTitle('UNGA AI Strategic Review')
    for index,flows in enumerate(prepared,1):
        y=height-38
        for flow in flows:
            w,h=flow.wrap(content_width,available);y-=h;flow.drawOn(canvas,44,y)
        canvas.setFont(font,7.5);canvas.setFillColor(colors.HexColor('#637382'))
        canvas.drawString(44,24,'UNGA AI Strategic Review | Automated source-grounded analysis | Evidence register supplied')
        canvas.drawRightString(width-44,24,f'{index} / {len(prepared)}');canvas.showPage()
    canvas.save()
    document=Document();section=document.sections[0]
    section.page_width=Inches(width/72);section.page_height=Inches(height/72)
    section.top_margin=section.bottom_margin=Inches(.52);section.left_margin=section.right_margin=Inches(44/72)
    normal=document.styles['Normal'];normal.font.name='Arial';normal.font.size=Pt(min(sizes))
    normal.paragraph_format.space_after=Pt(6);normal.paragraph_format.line_spacing=1.05
    document.styles['Heading 1'].font.size=Pt(17)
    for index,page in enumerate(report_pages):
        if index:document.add_page_break()
        for kind,value in page:
            if kind=='title':document.add_heading(value,1)
            elif kind=='image':document.add_picture(value,width=Inches(content_width/72))
            elif kind=='table':
                t=document.add_table(rows=0,cols=len(value[0]));t.style='Light Shading Accent 1'
                for row in value:
                    cells=t.add_row().cells
                    for cell,text in zip(cells,row):
                        cell.text=str(text)
                        for p in cell.paragraphs:
                            p.paragraph_format.space_after=Pt(2)
                            for run in p.runs:run.font.size=Pt(min(sizes)-1)
                for row in t.rows:
                    cant=OxmlElement('w:cantSplit');row._tr.get_or_add_trPr().append(cant)
            else:
                p=document.add_paragraph(value)
                if kind=='small':
                    for run in p.runs:run.font.size=Pt(min(sizes)-1)
    footer=section.footer.paragraphs[0];footer.text='UNGA AI Strategic Review | Automated source-grounded analysis | '
    field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');footer._p.append(field)
    docx=destination/(basename+'.docx');document.save(docx)
    import fitz
    word_verified=False;word_note='Word rendering unavailable; common-layout PDF used'
    if os.name=='nt' and use_word:
        word_pdf=destination/(basename+'.word-render.pdf')
        try:
            completed=subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',
                str(Path(__file__).with_name('render_word.ps1')),'-DocxPath',str(docx.resolve()),'-PdfPath',str(word_pdf.resolve())],
                capture_output=True,timeout=55,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if completed.returncode==0 and word_pdf.exists():
                with fitz.open(word_pdf) as word_document:
                    text='\n'.join(p.get_text() for p in word_document)
                    if not 4<=len(word_document)<=6 or not all(title in text for title in TITLES):
                        raise ValueError('Word-rendered report fails 4-6 page/section requirements')
                word_pdf.replace(pdf);word_verified=True;word_note='DOCX rendered by installed Microsoft Word; exported PDF is the delivered PDF'
        except (OSError,subprocess.TimeoutExpired):
            word_note='Word rendering did not complete; common-layout PDF used'
    with fitz.open(pdf) as check:
        if not 4<=len(check)<=6:raise ValueError('Report PDF must have 4-6 pages')
        full_text='\n'.join(p.get_text() for p in check)
        if not all(title in full_text for title in TITLES):raise ValueError('Missing report section in rendered PDF')
        for i,p in enumerate(check):
            p.get_pixmap(matrix=fitz.Matrix(1,1)).save(str(destination/f'report_page_{i+1}.png'))
        page_count=len(check)
    return dict(pdf=str(pdf),docx=str(docx),pdf_pages=page_count,pdf_layout_bounds_checked=True,
                docx_has_explicit_page_breaks=True,docx_render_verified=word_verified,docx_render_note=word_note,
                human_visual_review=False,font_sizes=sizes)
