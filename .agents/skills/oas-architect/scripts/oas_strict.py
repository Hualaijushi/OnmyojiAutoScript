"""OAS只读上下文加载器：只生成有界输出，不写项目／状态／缓存文件。"""
import argparse, hashlib, json, pathlib, re, subprocess, sys

def sha(b):return hashlib.sha256(b).hexdigest()

class ParseError(ValueError):pass

class Snapshot:
 def __init__(self,path,source_path=None):
  self.path=source_path or str(path);self.raw=path.read_bytes();self.source_reads=1;self.text=self.raw.decode('utf-8-sig',errors='strict');self.sha=sha(self.raw);self.lines=self.text.splitlines(keepends=True);self.fields=[];self.headings=[];self._parse()
 def _parse(self):
  stack=[];fence=None;events=[];offset=0
  for no,line in enumerate(self.lines,1):
   f=re.match(r'^ {0,3}(`{3,}|~{3,})(.*)',line)
   if f:
    mark=f[1]
    if fence is None:fence=mark
    elif mark[0]==fence[0] and len(mark)>=len(fence) and not f[2].strip():fence=None
    offset+=len(line);continue
   if fence:offset+=len(line);continue
   h=re.match(r'^(#{1,6})\s+(.+?)\s*$',line)
   if h:
    level=len(h[1]);title=h[2];stack=[x for x in stack if x['level']<level];item=dict(level=level,title=title,line=no,offset=offset);stack.append(item);self.headings.append(item);events.append((no,'heading',None))
   m=re.match(r'^\s*[-*+]\s+([^:：]+?)\s*[:：]\s*(.*?)(?:\r?\n)?$',line)
   if m:
    key=m[1].strip().strip('`*');field=dict(key=key,raw_name=m[1],raw_value=m[2],line=no,line_end=no,source_start=offset,source_end=offset+len(line),section=tuple((x['level'],x['title'],x['line']) for x in stack),raw_line=line);self.fields.append(field);events.append((no,'field',field))
   offset+=len(line)
  # 源码点和章节边界均来自同一快照，续行不跨下一个字段或标题。
  for i,event in enumerate(events):
   no,kind,field=event
   if kind!='field':continue
   end=events[i+1][0]-1 if i+1<len(events) else len(self.lines);tail=[]
   for n in range(no,end):
    line=self.lines[n]
    if line.startswith(('  ','\t')):tail.append(line.rstrip('\r\n'));field['line_end']=n+1
   if tail:field['raw_value']+='\n'+'\n'.join(tail)
   field['source_end']=sum(map(len,self.lines[:field['line_end']]))
  self.by_key={};self.duplicate_keys=[]
  for f in self.fields:
   self.by_key.setdefault(f['key'],[]).append(f)
  self.duplicate_keys=[k for k,v in self.by_key.items() if len(v)>1]
 def section(self,title):
  hits=[h for h in self.headings if h['title']==title]
  if len(hits)!=1:raise ParseError('标题缺失或歧义:'+title)
  h=hits[0];end=next((x['offset'] for x in self.headings if x['offset']>h['offset'] and x['level']<=h['level']),len(self.text));return self.text[h['offset']:end],(h['offset'],end)
 def task_list(self,title):
  hits=[h for h in self.headings if h['title']==title]
  if len(hits)!=1:raise ParseError('任务标题缺失或歧义')
  h=hits[0];a=h['line']-1;b=a+1
  while b<len(self.lines) and not self.lines[b].strip():b+=1
  first=b
  while b<len(self.lines) and (re.match(r'^[-*+]\s',self.lines[b]) or re.match(r'^\s+\S',self.lines[b])):b+=1
  if b==first:raise ParseError('任务列表缺失')
  end=sum(map(len,self.lines[:b]));return self.text[h['offset']:end],(h['offset'],end)

def category(field):
 title='/'.join(x[1] for x in field['section'][1:]) or '/'.join(x[1] for x in field['section'])
 if re.search('文件身份|任务合同|身份|合同',title):return 'A'
 if re.search('批准|权限',title):return 'B'
 if re.search('进度|实施|执行',title):return 'C'
 if re.search('验证|证据',title):return 'D'
 if re.search('验收|风险|接力|交接',title):return 'E'
 if re.search('基线|工作区',title):return 'H'
 return 'U'

def encode_paths(values):
 aliases={};encoded=list(values);all_text='\n'.join(values);candidates=set()
 for value in values:
  for path in re.findall(r'`([A-Za-z]:[\\/][^`]+)`',value):
   for match in re.finditer(r'[\\/]',path):
    prefix=path[:match.end()]
    if len(prefix)>=24:candidates.add(prefix)
 while candidates:
  joined='\n'.join(encoded);scored=[((len(p)-3)*joined.count(p)-len(p)-5,p) for p in candidates];gain,prefix=max(scored)
  if gain<=0:break
  token='~p'+str(len(aliases))+'~'
  if token in all_text:raise ParseError('路径别名冲突，不缩写原值')
  aliases[token]=prefix;encoded=[v.replace(prefix,token) for v in encoded];candidates.remove(prefix)
 return encoded,aliases

def decode_paths(text,aliases):return re.sub(r'~p\d+~',lambda m:aliases.get(m[0],m[0]),text)

DISPLAY_NAMES={'schema_version':'结构版','checkpoint_revision':'检查点','last_updated':'更新时间','controller':'控制者','update_rule':'写规则','task_id':'任务','current_phase':'阶段','objective':'目标','contract_version':'合同版','priority':'优先','contract_full_text':'主合同','contract_sha256':'主合同SHA','acceptance_criteria':'验收条件','completion_boundary':'完成边界','remediation_contract_full_text':'整改合同','remediation_contract_sha256':'整改合同SHA','remediation_authority':'整改授权','allowed_scope':'范围','allowed_files':'文件','forbidden_scope':'禁范围','approved_decisions':'有效决策','approval_reference':'批准依据','unauthorized_operations':'禁操作','lifecycle_status':'生命周期','implementation_status':'实施状态','implementation_scope':'实施范围','executor':'执行者','completed':'完成','pending':'待办','in_progress':'进行中','last_checkpoint':'上检查点','verification_status':'验证状态','verification_scope':'验证范围','test_commands':'命令','source_snapshot':'快照','passed':'通过','failed':'失败','skipped':'跳过','not_executed':'未执行','evidence_location':'证据','expired_evidence':'失效证据','acceptance_status':'验收状态','review_result':'审查','known_issues':'已知问题','unverified_behavior':'未验证','blockers':'阻塞','next_action':'下一步','required_approval':'待批准','handoff_notes':'交接','protected_existing_wip':'既有WIP','shared_file_rule':'共享文档规则','user_confirmed_wip':'用户WIP','remediation_scope':'历史整改范围'}

class BudgetStop(ValueError):pass
RESERVE=640
QUOTAS={'gateway':1300,'entry':5200,'rules':3300,'bootstrap':5500,'skill':2850,'git':1400,'current':5000}
CORE=('读取层级','安全预算与会话外精确审计','实际接收完整性','普通恢复最小路径','CURRENT 读写纪律')
# 这里只标记已解释的历史元数据；未识别键绝不按名字像baseline就隐藏。
HISTORY={'repository_root','worktree_path','git_common_dir','branch','HEAD','captured_at','staged_changes','unstaged_changes','untracked_files','baseline_manifest','baseline_snapshot','baseline_verification','baseline_diffs','remediation_baseline','final_review_baseline','t12_round2_baseline','t12_round2_contract','v3_v4_baseline','v3_v4_contract','v4_1_baseline','v4_1_contract','v4_2_baseline','v4_2_contract','v4_2_1_baseline','v4_2_2_baseline','v4_2_3_baseline','v4_2_4_baseline','v4_2_5_baseline','v4_2_1_review'}
def current_view(source):
 if not source.fields:raise ParseError('CURRENT没有可识别列表字段，不能用空投影冒充恢复')
 names=dict(DISPLAY_NAMES,active_contract='当前合同',v4_2_1_review='上轮审查')
 # 原键、原值和所属章节一直留在账本；历史引用只影响显示。
 selected=[f for f in source.fields if not(category(f)=='H' and f['key'] in HISTORY)]
 values,aliases=encode_paths([f['raw_value'] for f in selected]);visible={id(f):v for f,v in zip(selected,values)}
 rows=[];ledger=[];last=None;refs=[]
 for f in source.fields:
  historical=category(f)=='H' and f['key'] in HISTORY
  entry=dict(f,category=category(f),mode='reference' if historical else 'body',display_name=names.get(f['key'],f['key']));ledger.append(entry)
  if historical:refs.append(f);continue
  value=visible[id(f)];assert decode_paths(value,aliases)==f['raw_value']
  section=f['section'][-1] if f['section'] else (0,'未归属',0)
  if section!=last:rows.append(f'[{entry["category"]} {section[1]} @L{section[2]}]');last=section
  flag=' 待解释' if f['key'] not in names else ''
  rows.append(f'L{f["line"]} {entry["display_name"]}{flag}: {value}')
 if refs:rows.append('历史引用（非新授权，原名/值在缓存）：'+','.join('L'+str(f['line']) for f in refs))
 if source.duplicate_keys:raise ParseError('CURRENT重复键，保留歧义并停止：'+','.join(source.duplicate_keys))
 head=['路径等价缩写：']+[k+'='+v for k,v in aliases.items()] if aliases else []
 text='\n'.join(head+rows)+'\n'
 coverage=dict(parsed=len(source.fields),body=len(selected),reference=len(refs),unaccounted=0,unknown=sum(f['key'] not in names for f in selected),ledger_sha256=sha(json.dumps(ledger,ensure_ascii=False,sort_keys=True).encode('utf8')))
 return text,ledger,coverage

def source_range(source,start,end):
 return [source.text[:start].count('\n')+1,source.text[:max(start,end-1)].count('\n')+1,start,end]
def receipt_line(meta):
 return 'RECEIPT '+meta['mode']+' '+meta['plan_id']+' body_sha256='+meta['content_sha256']+'\n'
def make_frame(mode,body,sources=None,coverage=None,limit=6000):
 body=body.replace('\r\n','\n').replace('\r','\n')
 if '\x1b' in body:raise ParseError('正文含终端控制字符')
 if any(len(x)>800 for x in body.splitlines()):raise BudgetStop('必要正文有超长行，须明确报告而非截断')
 digest=sha(body.encode('utf8'));pid=sha((mode+digest).encode('utf8'))[:12]
 meta=dict(mode=mode,plan_id=pid,chunk_index=1,chunk_total=1,body_range=[0,len(body)],content_sha256=digest)
 if sources:meta['sources']=sources
 if coverage:meta['coverage']=coverage
 meta['estimated_with_wrapper']=0
 for _ in range(5):
  header=json.dumps(meta,ensure_ascii=False,separators=(',',':'))
  if len('BEGIN '+header)>800:header=json.dumps(meta,ensure_ascii=False,indent=0,separators=(',',':'))
  output='BEGIN '+header+'\nBODY\n'+body+'\nEND '+pid+'/1\n'
  estimate=len(output)+len(receipt_line(meta))+RESERVE
  if estimate==meta['estimated_with_wrapper']:break
  meta['estimated_with_wrapper']=estimate
 if any(len(x)>800 for x in output.splitlines()):raise BudgetStop('元数据行超过800字符，不截断')
 if estimate>limit:raise BudgetStop(f'{mode}必要信息预计{estimate}，可用{limit}；正文未交付，不删关键字段')
 return output
def receive(actual):
 # 从实收文本及正文长度截取验证，不接收生产者对象作为完成证明。
 if not actual.startswith('BEGIN '):raise ParseError('实收缺BEGIN或混入回显／包装')
 first=actual.index('\nBODY\n');meta=json.loads(actual[6:first]);a,b=meta['body_range'];first+=len('\nBODY')
 if a!=0 or b<0 or meta['chunk_index']!=1 or meta['chunk_total']!=1:raise ParseError('块数／偏移无效')
 body=actual[first+1:first+1+b];tail=actual[first+1+b:]
 if sha(body.encode('utf8'))!=meta['content_sha256']:raise ParseError('实收正文SHA不匹配')
 if tail!='\nEND '+meta['plan_id']+'/1\n':raise ParseError('尾标记缺失／重复／额外文本')
 if sha((meta['mode']+meta['content_sha256']).encode())[:12]!=meta['plan_id']:raise ParseError('计划不匹配')
 return meta,body

class Loader:
 def __init__(self,root,runner=None):self.root=pathlib.Path(root).resolve();self.cache={};self.runner=runner or self._run;self.reads={}
 def _run(self,args):
  p=subprocess.run(args,cwd=self.root,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  if p.returncode:raise ParseError('命令失败 '+str(p.returncode)+' '+p.stderr.decode('utf8',errors='replace'))
  if p.stderr:raise ParseError('命令有警告，未隐藏：'+p.stderr.decode('utf8',errors='replace'))
  return p.stdout
 def raw(self,path):
  path=pathlib.Path(path).resolve()
  if path not in self.cache:self.cache[path]=path.read_bytes();self.reads[str(path)]=self.reads.get(str(path),0)+1
  return self.cache[path]
 def source(self,relative):
  path=(self.root/relative).resolve()
  if not path.is_relative_to(self.root):raise ParseError('项目来源越界')
  class Cached:
   def read_bytes(inner):return self.raw(path)
  return Snapshot(Cached(),relative)
 def entry(self,memory_required=False,memory_file=None):
  parts=[];sources=[]
  if memory_required:
   p=pathlib.Path(memory_file) if memory_file else pathlib.Path.home()/'.codex/memories/MEMORY.md'
   if p.is_file():
    # 定向返回一个完整命中行；不展开固定行窗，不加载旧任务事实。
    raw=self.raw(p);text=raw.decode('utf-8-sig',errors='strict');lines=text.splitlines(keepends=True)
    patterns=(r'L0 budget is consumed before CURRENT',r'strict read-only context recovery',r'CURRENT parsing')
    hit=None
    for pattern in patterns:
     hits=[(n,line) for n,line in enumerate(lines,1) if re.search(pattern,line,re.I)]
     if hits:hit=hits[0];break
    if hit:
     n,line=hit;line=line.rstrip('\r\n')
     if len(line)>500:raise BudgetStop('定向记忆匹配行超过500字符；不展开历史或截断伪装完整')
     start=sum(map(len,lines[:n-1]));parts.append('[宿主定向记忆；不作当前项目事实]\nMEMORY.md:L'+str(n)+' '+line+'\n')
     sources.append(dict(path=str(p.resolve()),sha256=sha(raw),ranges=[[n,n,start,start+len(lines[n-1])]]))
    else:parts.append('[宿主定向记忆：无相关命中；停止记忆查找]\n')
   else:parts.append('[宿主定向记忆：文件不存在；不猜历史]\n')
  # ASCII发现入口只绑定raw指纹，不重复返回其正文；中文知识源同次缓存。
  gate=self.source('.agents/skills/oas-architect/SKILL.md')
  if not gate.text.isascii() or len(gate.raw)>600:raise ParseError('发现入口须为不超过600字节的ASCII，保持默认PowerShell首读兼容')
  sources.append(dict(path=gate.path,sha256=gate.sha,ranges=[],kind='launcher_fingerprint'))
  source=self.source('.agents/skills/oas-architect/references/context-loading.md');ranges=[]
  for title in ('架构师职责与边界',)+CORE:
   body,(a,b)=source.section(title);parts.append(body);ranges.append(source_range(source,a,b))
  sources.append(dict(path=source.path,sha256=source.sha,ranges=ranges))
  return '\n'.join(parts),sources
 def bootstrap(self):
  git=self.git();body,sources,coverage=self.document('current')
  return '[当前Git；与历史基线分开]\n'+git+'\n'+body,sources,coverage
 def document(self,mode):
  rel='.agents/skills/oas-architect/SKILL.md' if mode=='skill' else '.agents/skills/oas-architect/references/context-loading.md' if mode=='rules' else 'docs/CURRENT.md'
  s=self.source(rel);ranges=[];coverage=None
  if mode=='skill':body=s.text;ranges=[source_range(s,0,len(s.text))]
  elif mode=='rules':
   body=''
   for title in CORE:
    text,(a,b)=s.section(title);body+=text;ranges.append(source_range(s,a,b))
  else:body,ledger,coverage=current_view(s);ranges=[source_range(s,0,len(s.text))]
  return body,[dict(path=rel,sha256=s.sha,ranges=ranges)],coverage
 def git(self):
  def g(*args):return self.runner(['git','--no-optional-locks',*args]).decode('utf8').strip()
  root=g('rev-parse','--show-toplevel')
  if pathlib.Path(root).resolve()!=self.root:raise ParseError('脚本与当前worktree不一致')
  result=dict(repository_root=root,worktree_identity='same_as_root',branch=g('branch','--show-current'),HEAD=g('rev-parse','HEAD'))
  data=self.runner(['git','--no-optional-locks','status','--porcelain=v1','-z','--untracked-files=all']).decode('utf8').split('\0');i=0;counts={k:0 for k in ('staged_count','unstaged_count','untracked_count','deleted_count','renamed_count','conflict_count')}
  while i<len(data):
   item=data[i];i+=1
   if not item:continue
   if len(item)<4 or item[2]!=' ':raise ParseError('非法porcelain记录')
   xy=item[:2]
   if any(c not in ' MADRCU?!T' for c in xy):raise ParseError('未知porcelain状态')
   if xy=='??':counts['untracked_count']+=1;continue
   if xy=='!!':continue
   counts['staged_count']+=xy[0]!=' ';counts['unstaged_count']+=xy[1]!=' ';counts['deleted_count']+='D' in xy;counts['renamed_count']+='R' in xy;counts['conflict_count']+=xy in ('DD','AU','UD','UA','DU','AA','UU')
   if 'R' in xy or 'C' in xy:
    if i>=len(data) or not data[i]:raise ParseError('R/C旧路径缺失')
    i+=1
  return '\n'.join(k+': '+str(v) for k,v in dict(result,**counts).items())+'\n'
 def knowledge(self,kind):
  if kind=='core':
   parts=[];sources=[]
   for k in ('roadmap','testing','decision','context'):
    b,src=self.knowledge(k);parts.append(b);sources.extend(src)
   return '\n'.join(parts),sources
  mapping={'roadmap':('docs/ROADMAP.md','OAS Architect Skill V1.1（OAS-SKILL-V1）'),'testing':('docs/TESTING.md','8. OAS Architect Skill 与任务接力的验证'),'context':('docs/AI_CONTEXT.md','0.1 OAS Architect Skill 与任务接力（V1.1）'),'decision':('docs/DECISIONS.md',None)}
  rel,title=mapping[kind];s=self.source(rel)
  if title is None:
   hits=[h for h in s.headings if re.search(r'\bD063\b',h['title'])]
   if len(hits)!=1:raise ParseError('D063缺失／歧义')
   title=hits[0]['title']
  body,(a,b)=s.task_list(title) if kind=='roadmap' else s.section(title)
  return body,[dict(path=rel,sha256=s.sha,ranges=[source_range(s,a,b)])]
 def external_source(self,path):
  p=pathlib.Path(path).resolve()
  if p.suffix.lower() not in ('.md','.txt','.json'):raise ParseError('不支持的合同／证据格式')
  roots=[self.root,pathlib.Path('D:/Codex/workspace').resolve(),pathlib.Path('D:/Codex/outputs').resolve()]
  if not any(p.is_relative_to(root) for root in roots):raise ParseError('外部材料不在项目或Codex任务目录')
  class Cached:
   def read_bytes(inner):return self.raw(p)
  return Snapshot(Cached(),str(p))
 def contracts(self,records,active):
  if not records or not active:raise ParseError('合同记录／当前授权材料缺失')
  body=[];sources=[];active=pathlib.Path(active).resolve();active_found=False
  for path,want in records:
   if not re.fullmatch('[a-f0-9]{64}',want):raise ParseError('合同期望SHA非法')
   s=self.external_source(path)
   if s.sha!=want:raise ParseError('合同SHA不符：'+s.path)
   name=pathlib.Path(path).name;body.append(name+' SHA匹配（源元数据）')
   sources.append(dict(path=s.path,sha256=s.sha))
   if pathlib.Path(path).resolve()==active:
    active_found=True;picked=[]
    for n,line in enumerate(s.lines,1):
     if re.search('用户原话|范围|允许|禁止|边界|约束|授权',line):picked.append(f'L{n} '+line.rstrip('\r\n'))
    if not picked:raise ParseError('当前授权条款未识别，不用SHA冒充已核权限')
    body.extend(picked)
  if not active_found:raise ParseError('当前授权材料未在已核合同中')
  return '\n'.join(body)+'\n',sources
 def evidence(self,path,known):
  s=self.external_source(path);data=json.loads(s.text)
  if not isinstance(data.get('project_files'),dict) or not isinstance(data.get('unchanged_entries'),dict):raise ParseError('未识别快照schema，不能空匹配通过')
  records={}
  for rel,v in data['project_files'].items():
   if not isinstance(v,dict):raise ParseError('快照条目类型错误')
   records[rel]=v.get('after_sha256')
  if set(records)&data['unchanged_entries'].keys():raise ParseError('快照条目重复')
  records.update(data['unchanged_entries'])
  if not records or len(records)>32:raise ParseError('空快照或超普通核验范围，须另作专项审计')
  mandatory={'.agents/skills/oas-architect/SKILL.md','.agents/skills/oas-architect/references/context-loading.md','docs/CURRENT.md'}
  if not (mandatory & records.keys())<=known.keys():raise ParseError('请传此前实收source_sha，不能为快照重读已加载文档')
  rows=[]
  for rel,want in records.items():
   p=(self.root/rel).resolve()
   if not p.is_relative_to(self.root) or not re.fullmatch('[a-f0-9]{64}',str(want)):raise ParseError('快照路径／SHA非法')
   actual=known.get(rel) if rel in known else sha(self.raw(p))
   if actual!=want:raise ParseError('快照内容不匹配：'+rel)
   rows.append(rel+' MATCH '+('session_sha' if rel in known else 'read_once'))
  return '\n'.join(rows)+'\n',[dict(path=s.path,sha256=s.sha)]

def verify_stdin():
 data=json.load(sys.stdin)
 if not isinstance(data,dict) or set(data)!={'frames'} or not isinstance(data['frames'],list) or not 1<=len(data['frames'])<=3:raise ParseError('只核1～3份缓存实收；不合并正文返回')
 receipts=[];seen=set()
 for actual in data['frames']:
  if not isinstance(actual,str):raise ParseError('实收必须为原始文本')
  meta,body=receive(actual)
  if (meta['mode'],meta['plan_id']) in seen:raise ParseError('同模式实收重复，不能重复记通过')
  seen.add((meta['mode'],meta['plan_id']));receipts.append(receipt_line(meta))
 sys.stdout.write(''.join(receipts));return 0

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('skill','rules','git','current','knowledge','contracts','evidence','entry','bootstrap','materials','verify'));p.add_argument('--repo',type=pathlib.Path);p.add_argument('--remaining',type=int);p.add_argument('--spent',type=int);p.add_argument('--kind',choices=('roadmap','testing','decision','context','core'));p.add_argument('--contract',nargs=2,action='append',default=[]);p.add_argument('--active');p.add_argument('--snapshot');p.add_argument('--known',nargs=2,action='append',default=[]);p.add_argument('--memory-required',action='store_true');p.add_argument('--memory-file',type=pathlib.Path);a=p.parse_args(argv)
 sys.stdout.reconfigure(encoding='utf-8',errors='strict',newline='\n')
 try:
  if a.mode=='verify':return verify_stdin()
  if a.spent is not None and (a.mode!='bootstrap' or not 0<=a.spent<=12000):raise ParseError('spent仅用于bootstrap，须为已发生调用成本0～12000')
  if a.mode=='bootstrap' and a.remaining is not None and a.spent is None:raise ParseError('bootstrap默认已预留5500；自填remaining须附已发生成本spent，不猜剩余量')
  if a.spent is not None and a.remaining is not None and a.remaining>12000-a.spent:raise ParseError('remaining超过已知spent推导余量，不扩预算')
  if (a.memory_required or a.memory_file) and a.mode!='entry':raise ParseError('定向记忆仅entry模式可用')
  root=a.repo or pathlib.Path(__file__).resolve().parents[4]
  if not (root/'script.py').is_file() or not (root/'tasks').is_dir():raise ParseError('不是当前OAS根目录')
  loader=Loader(root);coverage=None;sources=None
  if a.mode=='entry':body,sources=loader.entry(a.memory_required,a.memory_file)
  elif a.mode=='bootstrap':body,sources,coverage=loader.bootstrap()
  elif a.mode in ('skill','rules','current'):body,sources,coverage=loader.document(a.mode)
  elif a.mode=='git':body=loader.git()
  elif a.mode=='knowledge':
   if not a.kind:raise ParseError('knowledge需要kind')
   body,sources=loader.knowledge(a.kind)
  elif a.mode=='contracts':body,sources=loader.contracts(a.contract,a.active)
  else:
   if not a.snapshot:raise ParseError('evidence/materials需要snapshot')
   known={k:v for k,v in a.known}
   if len(known)!=len(a.known) or any(not re.fullmatch('[a-f0-9]{64}',v) for v in known.values()):raise ParseError('known源SHA重复／非法')
   body,sources=loader.evidence(a.snapshot,known)
   if a.mode=='materials':
    contract,src=loader.contracts(a.contract,a.active);body=contract+'\n'+body;sources=src+sources
  limit=QUOTAS.get(a.mode,6000)
  if a.spent is not None:limit=min(limit,12000-a.spent)
  if a.remaining is not None:
   if a.remaining<0:raise ParseError('remaining不得负数')
   limit=min(limit,a.remaining)
  sys.stdout.write(make_frame(a.mode,body,sources,coverage,limit));return 0
 except (BudgetStop,ParseError,UnicodeError,OSError,ValueError,KeyError,TypeError,IndexError) as exc:
  sys.stdout.write('STOP '+json.dumps(dict(mode=a.mode,error_type=type(exc).__name__,reason=str(exc),body_delivered=False),ensure_ascii=False)+'\n');return 2
if __name__ == '__main__':
    if '--strict' not in sys.argv[1:]:
        sys.stdout.reconfigure(encoding='utf8', newline='\n')
        print('V1.1 兼容工具需要显式 --strict 和对应验收合同。')
        raise SystemExit(2)
    sys.argv.remove('--strict')
    raise SystemExit(main())
