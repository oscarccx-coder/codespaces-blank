"""Exact newest-owner workflow commands; model output cannot authorise work."""
import re

def parse_workflow_command(text):
    text=' '.join(str(text or '').split())
    if len(text)>650: return None
    if re.fullmatch(r'(?:list|show)\s+(?:apollo\s+)?workflows[.!?]?',text,re.I): return {'action':'list'}
    control=re.fullmatch(r'(status|pause|resume|stop)\s+workflow\s+([a-f0-9]{12})[.!?]?',text,re.I)
    if control: return {'action':control[1].lower(),'run_id':control[2].lower()}
    foundry=re.fullmatch(r'start\s+workflow\s+foundry\s+project\s+#?(\d{1,6})[.!]?',text,re.I)
    if foundry: return {'action':'start','workflow':'foundry_assessment','goal':'Assess Foundry project '+foundry[1],'project_id':int(foundry[1])}
    request=re.fullmatch(r'start\s+(?:(public)\s+)?workflow\s+(research|knowledge|benchmark|audit)\s+(?:about|on|:)\s*(.{5,400})',text,re.I)
    if request:
        kind={'research':'research_brief','knowledge':'knowledge_brief','benchmark':'application_benchmark','audit':'configuration_audit'}[request[2].lower()]
        goal=request[3]; target=re.search(r'\s+save\s+to\s+node\s+#?(\d{1,6})[.!]?$',goal,re.I); options={}
        if target: options={'target_node_id':int(target[1]),'index_memory':True}; goal=goal[:target.start()]
        return {'action':'start','workflow':kind,'goal':goal,'web_allowed':bool(request[1]),**options}
    return None

def handle_workflow_command(text,module):
    command=parse_workflow_command(text)
    if command is None: return None
    if module is None: return 'Enable Workflows & Learning in Apps, with Tools enabled in this persistent chat.'
    action=command['action']
    try: result=module.owner_action(action,**{k:v for k,v in command.items() if k!='action'})
    except (ValueError,PermissionError,KeyError,RuntimeError,OSError) as exc: return 'Workflow request failed: '+str(exc)
    if action=='list':
        return '**Apollo workflows:**\n'+('\n'.join(f"- {r['id']} · {r['state']} · {r['goal']}" for r in result[:20]) or 'No saved runs. Try **start public workflow research about local AI memory**.')
    lines=[f"**Workflow {result['id']}: {result['state']}**",'Goal: '+result['goal'],f"Stage: {result['current_stage']} ({result['completed_stages']}/{len(result['stages'])} committed)"]
    if action=='start': lines.append(f"Use **status workflow {result['id']}**, **pause workflow {result['id']}** or **stop workflow {result['id']}**. This is a finite run; continuous study remains in Practice & learning.")
    if result['last_error']: lines.append('Error: '+result['last_error'])
    if result['handoffs']: lines.append('Latest handoff: '+result['handoffs'][-1]['summary'])
    return '\n'.join(lines)
