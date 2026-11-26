"""Content-addressed binary attachment storage, shared across all conversations."""
import base64
import hashlib
import json

def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS attachment_blobs(
        digest TEXT PRIMARY KEY, data BLOB NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS attachment_links(
        chat TEXT NOT NULL, seq INTEGER NOT NULL, idx INTEGER NOT NULL,
        digest TEXT NOT NULL REFERENCES attachment_blobs(digest),
        PRIMARY KEY(chat,seq,idx),
        FOREIGN KEY(chat,seq) REFERENCES turns(chat,seq) ON DELETE CASCADE)""")
    db.execute('CREATE INDEX IF NOT EXISTS attachment_link_digest ON attachment_links(digest)')
    if 'blob_digest' not in {r[1] for r in db.execute('PRAGMA table_info(documents)')}:
        db.execute('ALTER TABLE documents ADD COLUMN blob_digest TEXT REFERENCES attachment_blobs(digest)')
    db.execute('CREATE INDEX IF NOT EXISTS document_blob_digest ON documents(blob_digest)')

def put(db,raw):
    digest=hashlib.sha256(raw).hexdigest()
    db.execute('INSERT OR IGNORE INTO attachment_blobs VALUES(?,?)',(digest,raw))
    return digest

def store(db,chat,seq,parts):
    db.execute('DELETE FROM attachment_links WHERE chat=? AND seq=?',(chat,seq))
    if not isinstance(parts,list):return parts
    out=[]
    for idx,p in enumerate(parts):
        kind=p.get('type')
        if kind=='binary_ref':raise ValueError('Internal attachment reference is not accepted.')
        if kind=='image_url':
            url=p['image_url']['url']
            head,sep,encoded=url.partition(',')
            if not sep or not head.startswith('data:') or not head.endswith(';base64'):
                out.append(p);continue
            raw=base64.b64decode(encoded,validate=True)
            meta={**p,'image_url':{**p['image_url'],'url':head+','}}
        elif kind=='input_audio':
            raw=base64.b64decode(p['input_audio']['data'],validate=True)
            meta={**p,'input_audio':{**p['input_audio'],'data':''}}
        else:out.append(p);continue
        digest=put(db,raw)
        db.execute('INSERT INTO attachment_links VALUES(?,?,?,?)',(chat,seq,idx,digest))
        out.append({'type':'binary_ref','meta':meta})
    return out

def restore(db,chat,seq,parts):
    if not isinstance(parts,list):return parts
    out=[]
    for idx,p in enumerate(parts):
        if p.get('type')!='binary_ref':out.append(p);continue
        row=db.execute("""SELECT b.data FROM attachment_links l JOIN attachment_blobs b
              ON b.digest=l.digest WHERE l.chat=? AND l.seq=? AND l.idx=?""",(chat,seq,idx)).fetchone()
        if row is None:raise ValueError('Stored attachment is missing.')
        encoded=base64.b64encode(row[0]).decode('ascii')
        meta=p['meta']
        if meta['type']=='image_url':meta['image_url']['url']+=encoded
        elif meta['type']=='input_audio':meta['input_audio']['data']=encoded
        else:raise ValueError('Invalid stored attachment.')
        out.append(meta)
    return out

def collect(db):
    db.execute("""DELETE FROM attachment_blobs WHERE NOT EXISTS
        (SELECT 1 FROM attachment_links l WHERE l.digest=attachment_blobs.digest)
        AND NOT EXISTS (SELECT 1 FROM documents d WHERE d.blob_digest=attachment_blobs.digest)""")

def migrate(db):
    init(db)
    # Content-only migration must not invalidate an existing chat summary.
    summaries=db.execute('SELECT chat,through,summary FROM chat_memory').fetchall()
    for row in db.execute("SELECT chat,seq,content FROM turns WHERE content LIKE '%image_url%' OR content LIKE '%input_audio%'").fetchall():
        chat,seq,value=row
        parts=json.loads(value)
        if isinstance(parts,list) and not any(p.get('type')=='binary_ref' for p in parts):
            packed=store(db,chat,seq,parts)
            if packed!=parts:db.execute('UPDATE turns SET content=? WHERE chat=? AND seq=?',(json.dumps(packed,ensure_ascii=False),chat,seq))
    for row in db.execute('SELECT id,raw FROM documents WHERE blob_digest IS NULL').fetchall():
        db.execute("UPDATE documents SET blob_digest=?,raw=X'' WHERE id=?",(put(db,row[1]),row[0]))
    db.executemany('INSERT OR REPLACE INTO chat_memory VALUES(?,?,?)',summaries)
    collect(db)
