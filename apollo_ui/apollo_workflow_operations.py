"""Deterministic verification and bounded workload benchmarks, not model training."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal,InvalidOperation
import json
import re
import secrets
from urllib.parse import urlsplit

def application_questions():
    batches,pages=secrets.randbelow(15)+3,secrets.randbelow(5)+2
    seconds=secrets.randbelow(30)+20; tokens=(secrets.randbelow(20)+5)*seconds
    budget,cost=(secrets.randbelow(10)+3)*60,secrets.randbelow(60)+30
    return {'questions':[
        {'id':'page_budget','skill':'workload planning','question':f'A research task has {batches} batches, each attempting {pages} pages. Exactly one page per batch fails. How many pages were fetched successfully? Answer only a number.'},
        {'id':'throughput','skill':'quantitative reasoning','question':f'A local model produces {tokens} output tokens in {seconds} seconds. What is the output tokens per second rate? Answer only a number.'},
        {'id':'time_budget','skill':'resource planning','question':f'A job has a {budget}-second budget. Each full batch takes {cost} seconds. How many complete batches fit? Answer only an integer.'},
        {'id':'evidence','skill':'source independence','question':'Two articles copy the same press release. Is this two independent confirmations? Answer yes or no.'}],
        'answer_key':[str(batches*(pages-1)),str(tokens//seconds),str(budget//cost),'no'],
        'notice':'Fresh narrow workload/evidence problems; not a test of topic expertise or broad intelligence.'}

def grade_application(bundle,response):
    if isinstance(response,str): response=json.loads(response)
    submitted=response.get('answers') if isinstance(response,dict) else None
    if not isinstance(submitted,list) or len(submitted)!=len(bundle['questions']): raise ValueError('Return exactly one answer per application question.')
    rows=[]
    for index,question in enumerate(bundle['questions']):
        expected,attempt=bundle['answer_key'][index],str(submitted[index])[:100].strip()
        try: correct=Decimal(attempt).is_finite() and Decimal(attempt)==Decimal(expected)
        except InvalidOperation: correct=attempt.casefold()==expected.casefold()
        rows.append({**question,'expected':expected,'attempt':attempt,'correct':bool(correct)})
    correct=sum(r['correct'] for r in rows)
    return {'correct':correct,'total':len(rows),'exercises':rows,'notice':bundle['notice'],
            'contract_passed':True,'summary':f'Measured exact application score {correct}/{len(rows)}; no model self-grading.'}

def check_quotations(sources,lesson):
    from apollo_practice import public_sources
    allowed={s['url']:s['text'] for s in public_sources(sources)}; claims=lesson.get('claims') or []
    if not claims or not all(c.get('url') in allowed and c.get('quote') and c['quote'] in allowed[c['url']] for c in claims):
        raise ValueError('Lesson lacks exact supporting quotations from fetched sources.')
    return {'contract_passed':True,'claims_checked':len(claims),'summary':'Quotation provenance checked; summaries and source truth remain unverified.'}

def check_memory_citations(packet,brief):
    ids=set(re.findall(r'\[memory:(\d+)\]',str(brief))); allowed={str(i) for i in packet.get('memory_ids',[])}
    if not ids or not ids<=allowed: raise ValueError('Brief must cite actual retrieved memory IDs; citation missing or invented.')
    return {'contract_passed':True,'memory_ids':sorted(ids),'summary':'Memory citation IDs matched the retrieved packet; semantic accuracy still needs review.'}

def configuration_audit(config,runtime=None,capabilities=()):
    findings=[]
    try:
        endpoint=urlsplit(str(config.get('ollama_url',''))); local=endpoint.hostname in ('localhost','127.0.0.1','::1')
        if endpoint.username or endpoint.password: findings.append({'severity':'warning','check':'endpoint_credentials','detail':'Credentials embedded in model URL; values redacted.'})
    except ValueError: local=False
    if not local: findings.append({'severity':'warning','check':'external_endpoint','detail':'Endpoint is not loopback; local workflow generation will be refused.'})
    if 'cloud' in str(config.get('model','')).casefold(): findings.append({'severity':'warning','check':'cloud_model','detail':'Cloud-labelled model selected; local workflow generation will be refused.'})
    granted=[]
    if runtime is not None:
        for capability in sorted(set(capabilities)):
            if runtime.risk_for(capability)=='high' and runtime.get_permission(capability)=='allow': granted.append(capability)
        if granted: findings.append({'severity':'review','check':'high_risk_grants','detail':f'{len(granted)} registered high-risk capabilities are allowed. Review in Core Services.'})
    return {'endpoint_scope':'loopback' if local else 'external_or_invalid','high_risk_capabilities':granted[:100],
        'findings':findings,'contract_passed':True,'summary':f'Read-only configuration audit: {len(findings)} findings; no settings changed.',
        'notice':'Limited configuration review only; not AgentShield, a malware scan or a guarantee of safety. Secret values are not included.'}

def curriculum_from_service(service):
    if service is None: return {'topics':[],'notice':'Enable Learning Missions to see saved practice.'}
    with service.store.lock:
        rows=service.store.db.execute('''SELECT m.id,m.title,m.goal,p.step_no,p.lesson_json,e.created_at
          FROM practice_cycles p JOIN missions m ON m.id=p.mission_id JOIN evidence e ON e.mission_id=p.mission_id AND e.step_no=p.step_no
          WHERE p.error='' ORDER BY e.id DESC LIMIT 2000''').fetchall()
    topics={}
    for row in reversed(rows):
        lesson=json.loads(row['lesson_json'])
        item=topics.setdefault(row['id'],{'mission_id':row['id'],'title':row['title'],'goal':row['goal'],'concepts':{},'batches':0,'correct':0,'total':0,'application_correct':0,'application_total':0})
        item['batches']+=1; item['correct']+=lesson.get('correct',0); item['total']+=lesson.get('total',0)
        app=lesson.get('application') or {}; item['application_correct']+=app.get('correct',0); item['application_total']+=app.get('total',0)
        for exercise in lesson.get('exercises',[]):
            concept=str(exercise.get('concept') or 'Recall')[:160]
            c=item['concepts'].setdefault(concept,{'concept':concept,'attempts':0,'correct':0})
            c['attempts']+=1; c['correct']+=int(bool(exercise.get('correct'))); c['last_passed']=bool(exercise.get('correct'))
            date=datetime.fromisoformat(row['created_at'])
            if date.tzinfo is None: date=date.replace(tzinfo=timezone.utc)
            due=date+timedelta(days=7 if c['last_passed'] else 1)
            c['next_review']=due.isoformat(timespec='seconds'); c['due']=due<=datetime.now(timezone.utc)
        item['next_gap']=lesson.get('next_question','')
    for item in topics.values(): item['concepts']=list(item['concepts'].values())
    return {'topics':list(topics.values()),'inspected_batches':len(rows),'limit':2000,
      'notice':'Observed recall and narrow application results, not mastery or weight training. Review dates are suggestions; existing practice missions control execution.'}
