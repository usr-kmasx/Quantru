"""Bounded local document extraction and lexical retrieval."""
import base64
import csv
import io
import pathlib
import re
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET

MAX_FILE=20*1024*1024
MAX_TEXT=8_000_000
EXTS={'.pdf','.docx','.xlsx','.txt','.md','.markdown','.csv','.tsv','.json','.xml','.yaml','.yml','.toml','.ini','.cfg','.conf','.log','.rst','.py','.js','.ts','.jsx','.tsx','.html','.css','.c','.h','.cpp','.hpp','.rs','.go','.java','.kt','.sh','.bash','.zsh','.fish','.sql','.rb','.php','.lua','.swift','.cs','.vue','.svelte','.cmake','.dockerfile'}
SPECIAL={'makefile','dockerfile','cmakelists.txt','readme','license'}
def extension(name):
    return pathlib.PurePath(name).suffix.lower()
def init(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS documents(
      id INTEGER PRIMARY KEY,chat TEXT NOT NULL,seq INTEGER NOT NULL,idx INTEGER NOT NULL,
      name TEXT NOT NULL,ext TEXT NOT NULL,raw BLOB NOT NULL,units INTEGER NOT NULL,
      UNIQUE(chat,seq,idx),FOREIGN KEY(chat,seq) REFERENCES turns(chat,seq) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS document_chunks(
      id INTEGER PRIMARY KEY,doc INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
      unit INTEGER NOT NULL,location TEXT NOT NULL,body TEXT NOT NULL,visual INTEGER NOT NULL DEFAULT 0);
    CREATE INDEX IF NOT EXISTS document_chat ON documents(chat,seq);
    CREATE INDEX IF NOT EXISTS document_chunk_doc ON document_chunks(doc,unit);
    CREATE VIRTUAL TABLE IF NOT EXISTS document_search USING fts5(body,location,tokenize='unicode61 remove_diacritics 2');
    CREATE TRIGGER IF NOT EXISTS document_chunk_insert AFTER INSERT ON document_chunks BEGIN
      INSERT INTO document_search(rowid,body,location) VALUES(new.id,new.body,new.location);
    END;
    CREATE TRIGGER IF NOT EXISTS document_chunk_delete AFTER DELETE ON document_chunks BEGIN
      DELETE FROM document_search WHERE rowid=old.id;
    END;
    """)
def run(args,timeout=45):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    if p.returncode:raise ValueError('Unable to read document: '+p.stderr.decode(errors='replace')[-300:])
    return p.stdout
def xml(z,name):
    try:
        info=z.getinfo(name)
        if info.file_size>MAX_TEXT:raise ValueError('Document XML is too large.')
        raw=z.read(info)
    except KeyError:return None
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('Unsupported XML declaration.')
    return ET.fromstring(raw)
def local(tag):return tag.rsplit('}',1)[-1]
def chunks(text,label,unit,visual=False):
    # Bounded overlapping chunks with original line ranges.
    lines=text.splitlines() or ['']
    result=[];i=0
    while i<len(lines):
        end=i;count=0
        while end<len(lines) and end-i<60 and (count+len(lines[end])<=2800 or end==i):
            count+=len(lines[end])+1;end+=1
        body='\n'.join(f'{n+1}: {lines[n]}' for n in range(i,end))
        for offset in range(0,max(1,len(body)),2400):
            result.append((unit,f'{label}, lines {i+1}-{end}',body[offset:offset+2800],int(visual)))
        if end==len(lines):break
        i=max(i+1,end-5)
    return result
def extract(name,raw):
    ext=extension(name)
    if ext not in EXTS and name.lower() not in SPECIAL:raise ValueError('Unsupported document type: '+name)
    if not raw or len(raw)>MAX_FILE:raise ValueError('Documents must be between 1 byte and 20 MiB.')
    rows=[];units=0
    if ext=='.pdf':
        with tempfile.TemporaryDirectory(prefix='quantru-doc-') as tmp:
            path=pathlib.Path(tmp)/'document.pdf';path.write_bytes(raw)
            info=run(['pdfinfo',str(path)]).decode(errors='replace')
            match=re.search(r'^Pages:\s*(\d+)',info,re.M)
            units=int(match.group(1)) if match else 0
            if not 1<=units<=2000:raise ValueError('PDF limit: 2000 pages.')
            text=run(['pdftotext','-layout',str(path),'-']).decode(errors='replace')
            if len(text)>MAX_TEXT:raise ValueError('Extracted document text exceeds 8 million characters.')
            pages=text.split('\f')
            for i in range(units):
                page=pages[i] if i<len(pages) else ''
                visual=len(re.sub(r'\s','',page))<40
                rows+=chunks(page,f'page {i+1}',i+1,visual)
    elif ext in ('.docx','.xlsx'):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if len(z.infolist())>10000 or sum(x.file_size for x in z.infolist())>100*1024*1024:raise ValueError('Expanded Office document is too large.')
            if ext=='.docx':
                root=xml(z,'word/document.xml')
                if root is None:raise ValueError('Invalid DOCX.')
                paragraphs=[]
                body=next((n for n in root if local(n.tag)=='body'),root)
                def paragraph(el):return ''.join(n.text or '' for n in el.iter() if local(n.tag)=='t')
                for el in body:
                    if local(el.tag)=='tbl':
                        for tr in el:
                            if local(tr.tag)=='tr':
                                paragraphs.append(' | '.join(paragraph(tc) for tc in tr if local(tc.tag)=='tc'))
                    elif local(el.tag)=='p':paragraphs.append(paragraph(el))
                    else:
                        paragraphs.extend(paragraph(n) for n in el.iter() if local(n.tag)=='p')
                units=1;rows=chunks('\n'.join(paragraphs),'document',1)
            else:
                book=xml(z,'xl/workbook.xml');rels=xml(z,'xl/_rels/workbook.xml.rels')
                if book is None or rels is None:raise ValueError('Invalid XLSX.')
                shared=xml(z,'xl/sharedStrings.xml')
                strings=[''.join(n.text or '' for n in el.iter() if local(n.tag)=='t') for el in shared] if shared is not None else []
                targets={x.attrib.get('Id'):x.attrib.get('Target','') for x in rels}
                for sheet in book.iter():
                    if local(sheet.tag)!='sheet':continue
                    rid=next((v for k,v in sheet.attrib.items() if local(k)=='id'),'')
                    target=targets.get(rid,'')
                    path=target.lstrip('/') if target.startswith('/') else 'xl/'+target
                    root=xml(z,path)
                    if root is None:continue
                    units+=1;lines=[]
                    for row in root.iter():
                        if local(row.tag)!='row':continue
                        cells=[]
                        for cell in row:
                            if local(cell.tag)!='c':continue
                            v=next((n.text or '' for n in cell if local(n.tag)=='v'),'')
                            if cell.attrib.get('t')=='s':
                                v=strings[int(v)] if v.isdigit() and int(v)<len(strings) else v
                            elif cell.attrib.get('t')=='inlineStr':v=''.join(n.text or '' for n in cell.iter() if local(n.tag)=='t')
                            f=next((n.text for n in cell if local(n.tag)=='f'),None)
                            if f:v+=' [formula: ='+f+']'
                            cells.append(cell.attrib.get('r','')+'='+v)
                        lines.append('row '+row.attrib.get('r','?')+': '+' | '.join(cells))
                    rows+=chunks('\n'.join(lines),'sheet '+sheet.attrib.get('name','?'),units)
    else:
        if b'\x00' in raw and not raw.startswith((b'\xff\xfe',b'\xfe\xff')):raise ValueError('Not a supported text document.')
        try:text=raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
        except UnicodeDecodeError:text=raw.decode('cp1252',errors='replace')
        if len(text)>MAX_TEXT:raise ValueError('Document text exceeds 8 million characters.')
        units=1;rows=chunks(text,'document',1)
    if not rows:raise ValueError('No readable document content.')
    if sum(len(r[2]) for r in rows)>MAX_TEXT*3:raise ValueError('Document index exceeds size limit.')
    return ext,units,rows
def prepare(parts):
    if not isinstance(parts,list):return []
    prepared=[]
    for idx,p in enumerate(x for x in parts if isinstance(x,dict) and x.get('type')!='text'):
        if p.get('type')!='document':continue
        name=pathlib.PurePath(str(p.get('name',''))).name[:200]
        try:raw=base64.b64decode(p['data'],validate=True)
        except (KeyError,ValueError,TypeError):raise ValueError('Invalid document attachment.')
        try:ext,units,rows=extract(name,raw)
        except (OSError,zipfile.BadZipFile,ET.ParseError,subprocess.TimeoutExpired) as e:raise ValueError(f'Unable to read {name}: {e}') from e
        prepared.append((idx,name,raw,ext,units,rows))
    return prepared
def store(db,chat,seq,parts,prepared):
    if not isinstance(parts,list):return parts
    by_idx={r[0]:r for r in prepared}
    keep=[];out=[];idx=-1
    for p in parts:
        if p.get('type')=='text':out.append(p);continue
        idx+=1
        if p.get('type')=='document':
            _,name,raw,ext,units,rows=by_idx[idx]
            db.execute('DELETE FROM documents WHERE chat=? AND seq=? AND idx=?',(chat,seq,idx))
            from . import attachment_store
            digest=attachment_store.put(db,raw)
            id=db.execute('INSERT INTO documents(chat,seq,idx,name,ext,raw,units,blob_digest) VALUES(?,?,?,?,?,?,?,?)',(chat,seq,idx,name,ext,b'',units,digest)).lastrowid
            db.executemany('INSERT INTO document_chunks(doc,unit,location,body,visual) VALUES(?,?,?,?,?)',((id,*r) for r in rows))
        elif p.get('type')=='document_ref':
            row=db.execute('SELECT id,name FROM documents WHERE chat=? AND seq=? AND idx=? AND id=?',(chat,seq,idx,p.get('id'))).fetchone()
            if not row:raise ValueError('Document reference not found.')
            id,name=row
        else:out.append(p);continue
        keep.append(id);out.append({'type':'document_ref','id':id,'name':name})
    for row in db.execute('SELECT id FROM documents WHERE chat=? AND seq=?',(chat,seq)).fetchall():
        if row[0] not in keep:db.execute('DELETE FROM documents WHERE id=?',(row[0],))
    return out
def model_content(parts):
    if not isinstance(parts,list):return parts
    result=[p for p in parts if p.get('type')!='document_ref']
    names=[p['name'] for p in parts if p.get('type')=='document_ref']
    if names:result.append({'type':'text','text':'[Attached documents: '+', '.join(names)+']'})
    return result
def lookup(db,chat,seq,question):
    from .context_memory import keywords
    docs=db.execute('SELECT id,name,ext,units,seq FROM documents WHERE chat=? AND seq<=? ORDER BY seq DESC,id DESC LIMIT 24',(chat,seq)).fetchall()
    if not docs:return [],[],[]
    terms=keywords(question);matches=[]
    if terms:
        query=' OR '.join('"'+w.replace('"','""')+'"' for w in terms)
        matches=db.execute("""SELECT c.*,d.name,d.seq FROM document_search JOIN document_chunks c ON c.id=document_search.rowid
        JOIN documents d ON d.id=c.doc WHERE document_search MATCH ? AND d.chat=? AND d.seq<=?
        ORDER BY (d.seq=? ) DESC,bm25(document_search) LIMIT 30""",(query,chat,seq,seq)).fetchall()
    pages=[int(n) for n in re.findall(r'(?:p[aá]ginas?|pages?|p\.)\s*(\d+)',question,re.I) if 0<int(n)<=2000]
    selected=[];seen=set()
    def add(row):
        if row['id'] not in seen:
            seen.add(row['id']);selected.append(row)
    for d in docs:
        if pages and d['ext']=='.pdf':
            for page in pages:
                for r in db.execute('SELECT c.*,d.name,d.seq FROM document_chunks c JOIN documents d ON d.id=c.doc WHERE c.doc=? AND c.unit=? ORDER BY c.id LIMIT 12',(d['id'],page)):add(r)
    for r in matches:add(r)
    for d in docs[:6]:
        for r in db.execute('SELECT c.*,d.name,d.seq FROM document_chunks c JOIN documents d ON d.id=c.doc WHERE c.doc=? ORDER BY c.id LIMIT 3',(d['id'],)):add(r)
    visual=[]
    want_visual=bool(re.search(r'gr[aá]fico|diagram|imagem|image|figure|figura|visual|chart|scan|digitalizad',question,re.I))
    for d in docs:
        if d['ext']!='.pdf':continue
        targets=[p for p in pages if p<=d['units']]
        if not targets:
            targets=[r[0] for r in db.execute('SELECT DISTINCT unit FROM document_chunks WHERE doc=? AND visual=1 ORDER BY unit LIMIT 2',(d['id'],))]
        if not targets and want_visual:targets=list(dict.fromkeys(r['unit'] for r in selected if r['doc']==d['id']))[:2]
        for page in targets:visual.append((d['id'],d['name'],page))
    return docs,selected[:36],visual[:4]
def render_page(db,id,page):
    row=db.execute('SELECT COALESCE(b.data,d.raw) FROM documents d LEFT JOIN attachment_blobs b ON b.digest=d.blob_digest WHERE d.id=?',(id,)).fetchone()
    if not row:return None
    with tempfile.TemporaryDirectory(prefix='quantru-page-') as tmp:
        path=pathlib.Path(tmp)/'document.pdf';path.write_bytes(row[0])
        return run(['pdftoppm','-f',str(page),'-l',str(page),'-scale-to','1400','-singlefile','-png',str(path)],30)
