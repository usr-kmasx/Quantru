"""Local SQLite chat archive. Pages never include attachment bodies."""
import contextlib
import hashlib
import json
import pathlib
import re
import sqlite3
import time
import uuid
from . import documents, attachment_store

DB = pathlib.Path(__file__).resolve().parent / 'chats.sqlite3'
PAGE = 12

@contextlib.contextmanager
def connect():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()

def init():
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript("""
        CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY,title TEXT NOT NULL,updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS turns(chat TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
          seq INTEGER NOT NULL,text TEXT NOT NULL,answer TEXT NOT NULL DEFAULT '',
          thinking TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'pending',
          content TEXT NOT NULL,files TEXT NOT NULL,PRIMARY KEY(chat,seq));
        CREATE INDEX IF NOT EXISTS chats_updated ON chats(updated DESC,id);
        CREATE TABLE IF NOT EXISTS generated_images(
          chat TEXT NOT NULL,seq INTEGER NOT NULL,png BLOB NOT NULL,prompt TEXT NOT NULL,
          PRIMARY KEY(chat,seq), FOREIGN KEY(chat,seq) REFERENCES turns(chat,seq) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS shell_runs(
          chat TEXT NOT NULL,seq INTEGER NOT NULL,idx INTEGER NOT NULL,
          command TEXT NOT NULL,cwd TEXT NOT NULL,output TEXT NOT NULL DEFAULT '',
          exit_code INTEGER,status TEXT NOT NULL DEFAULT 'running',
          PRIMARY KEY(chat,seq,idx),FOREIGN KEY(chat,seq) REFERENCES turns(chat,seq) ON DELETE CASCADE);
        UPDATE shell_runs SET status='interrupted' WHERE status='running';
        """)
        if 'generation_id' not in {r[1] for r in db.execute('PRAGMA table_info(turns)')}:
            db.execute('ALTER TABLE turns ADD COLUMN generation_id TEXT')
        if 'generation_stats' not in {r[1] for r in db.execute('PRAGMA table_info(turns)')}:
            db.execute('ALTER TABLE turns ADD COLUMN generation_stats TEXT')
        if 'thinking_boundaries' not in {r[1] for r in db.execute('PRAGMA table_info(turns)')}:
            db.execute('ALTER TABLE turns ADD COLUMN thinking_boundaries TEXT')
        db.execute("UPDATE turns SET status='stopped' WHERE status='pending'")
        from . import context_memory
        context_memory.init(db)
        documents.init(db)
        attachment_store.migrate(db)
    # Enable full auto-vacuum once, including for existing archives. It returns
    # deleted pages to the filesystem after commit/checkpoint.
    with connect() as db:
        if db.execute('PRAGMA auto_vacuum').fetchone()[0]!=1:
            db.execute('PRAGMA auto_vacuum=FULL')
            db.execute('VACUUM')
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    DB.chmod(0o600)

def ident(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9-]{36}',value):
        raise ValueError('Invalid chat ID')
    return value

def seqnum(value):
    if type(value) is not int or not 1 <= value <= 1000000000:
        raise ValueError('Invalid message number')
    return value

def list_chats(offset=0):
    with connect() as db:
        rows=db.execute('SELECT id,title,updated FROM chats ORDER BY updated DESC,id LIMIT 51 OFFSET ?', (max(0,offset),)).fetchall()
    return {'chats':[dict(r) for r in rows[:50]],'more':len(rows)>50}

def page(chat,before=None):
    ident(chat)
    with connect() as db:
        revision=db.execute('SELECT updated FROM chats WHERE id=?',(chat,)).fetchone()
        if not revision: raise ValueError('Chat not found')
        rows=db.execute('SELECT seq,text,answer,thinking,status,files,generation_stats,thinking_boundaries,EXISTS(SELECT 1 FROM generated_images g WHERE g.chat=turns.chat AND g.seq=turns.seq) AS generated_image FROM turns WHERE chat=? AND seq<? ORDER BY seq DESC LIMIT ?', (chat,before or 1000000001,PAGE+1)).fetchall()
        turns=[dict(r,files=json.loads(r['files']),generation_stats=json.loads(r['generation_stats']) if r['generation_stats'] else None) for r in reversed(rows[:PAGE])]
        for turn in turns:
            turn['thinking_boundaries']=json.loads(turn['thinking_boundaries']) if turn['thinking_boundaries'] else []
            turn['shell_runs']=[dict(r) for r in db.execute('SELECT idx,command,cwd,output,exit_code,status FROM shell_runs WHERE chat=? AND seq=? ORDER BY idx',(chat,turn['seq']))]
    return {'turns':turns,'more':len(rows)>PAGE,'revision':revision[0]}

def content(chat,seq):
    with connect() as db:
        row=db.execute('SELECT content FROM turns WHERE chat=? AND seq=?',(ident(chat),seqnum(seq))).fetchone()
        if row is None: raise ValueError('Message not found')
        return attachment_store.restore(db,chat,seq,json.loads(row[0]))

def sync_state(chat):
    from . import chat_sync
    with connect() as db:
        db.execute('BEGIN')
        rows=db.execute('SELECT id,title,updated FROM chats ORDER BY id').fetchall()
        revision=next((r['updated'] for r in rows if r['id']==chat),None)
        digest=hashlib.sha256(json.dumps([tuple(r) for r in rows],ensure_ascii=False).encode()).hexdigest()
        pending=db.execute("SELECT seq FROM turns WHERE chat=? AND status='pending' ORDER BY seq DESC LIMIT 1",(chat,)).fetchone()
    live=chat_sync.get(chat)
    return {'list_revision':digest,'revision':revision,'pending':pending[0] if pending else None,'live':live}

def verify_generation(chat,seq,owner):
    with connect() as db:
        row=db.execute('SELECT generation_id,status FROM turns WHERE chat=? AND seq=?',(ident(chat),seqnum(seq))).fetchone()
        if not row or row[0]!=owner or row[1]!='pending':raise ValueError('This message is no longer awaiting generation.')

def mutate(op,d):
    chat=ident(d['chat'])
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        from . import chat_sync
        if op in ('begin','delete') and chat_sync.get(chat):raise ValueError('This chat is generating on another device.')
        current=db.execute('SELECT updated FROM chats WHERE id=?',(chat,)).fetchone()
        revision=current[0] if current else None
        if op=='begin' and 'expected_revision' in d and revision!=d['expected_revision']:
            raise ValueError('Chat changed on another device. Your message was not sent. Try again.')
        if op in ('begin','delete'):
            pending=db.execute("SELECT 1 FROM turns WHERE chat=? AND status='pending' AND generation_id IS NOT NULL",(chat,)).fetchone()
            if pending and revision is not None and time.time()-revision<45:
                raise ValueError('This chat is generating on another device.')
        if op=='delete':
            db.execute('DELETE FROM chats WHERE id=?',(chat,))
            attachment_store.collect(db)
            db.commit()
            # A checkpoint releases the WAL after auto-vacuum has moved
            # live pages and truncated the logical database. Readers may
            # defer it; never fail an already committed deletion.
            try:db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            except sqlite3.OperationalError:pass
            return {}
        if op=='rename':
            title=d['title'].strip()[:100]
            if not title: raise ValueError('Title required')
            db.execute('UPDATE chats SET title=? WHERE id=?',(title,chat))
            return {}
        seq=seqnum(d['seq'])
        if op=='begin':
            text=d['text']; files=d['files']; value=d['content']
            if not isinstance(text,str) or not isinstance(files,list) or not isinstance(value,(str,list)): raise ValueError('Invalid message')
            if len(files)>16: raise ValueError('Too many attachments')
            owner=d.get('generation_id')
            if owner is not None:ident(owner)
            if d.get('mode')=='append':
                latest=db.execute('SELECT COALESCE(max(seq),0) FROM turns WHERE chat=?',(chat,)).fetchone()[0]
                if seq!=latest+1:raise ValueError('Chat changed on another device. Your message was not sent. Try again.')
            if d.get('mode')=='replace' and not db.execute('SELECT 1 FROM turns WHERE chat=? AND seq=?',(chat,seq)).fetchone():
                raise ValueError('Message no longer exists.')
            prepared=documents.prepare(value)
            title=' '.join(text.split())[:70] or (prepared[0][1][:70] if prepared else 'Attachment')
            db.execute('INSERT OR IGNORE INTO chats VALUES(?,?,?)',(chat,title,time.time()))
            # Editing/retrying an existing turn replaces its later branch.
            db.execute('DELETE FROM turns WHERE chat=? AND seq>?',(chat,seq))
            db.execute('DELETE FROM generated_images WHERE chat=? AND seq=?',(chat,seq))
            db.execute('DELETE FROM shell_runs WHERE chat=? AND seq=?',(chat,seq))
            db.execute("""INSERT INTO turns(chat,seq,text,content,files,generation_id) VALUES(?,?,?,?,?,?)
                 ON CONFLICT(chat,seq) DO UPDATE SET text=excluded.text,content=excluded.content,files=excluded.files,
                 answer='',thinking='',status='pending',generation_stats=NULL,thinking_boundaries=NULL,generation_id=excluded.generation_id""",(chat,seq,text,json.dumps(text,ensure_ascii=False),json.dumps(files,ensure_ascii=False),owner))
            value=documents.store(db,chat,seq,value,prepared)
            value=attachment_store.store(db,chat,seq,value)
            db.execute('UPDATE turns SET content=? WHERE chat=? AND seq=?',(json.dumps(value,ensure_ascii=False),chat,seq))
            attachment_store.collect(db)
        elif op=='finish':
            state=d['status']
            if state not in ('complete','stopped','error'): raise ValueError('Invalid status')
            row=db.execute('SELECT generation_id,status FROM turns WHERE chat=? AND seq=?',(chat,seq)).fetchone()
            if not row or row[0]!=d.get('generation_id'):raise ValueError('Message was changed on another device.')
            if row[1]!='pending' and row[0] is not None:return {'revision':revision}
            live=chat_sync.get(chat)
            metrics=live.get('generation_stats') if live else None
            boundaries=live.get('thinking_boundaries',[]) if live else []
            db.execute('UPDATE turns SET answer=?,thinking=?,status=?,generation_stats=?,thinking_boundaries=? WHERE chat=? AND seq=?',
                       (d['answer'],d['thinking'],state,json.dumps(metrics) if metrics else None,json.dumps(boundaries) if boundaries else None,chat,seq))
        else: raise ValueError('Unknown operation')
        revision=time.time()
        db.execute('UPDATE chats SET updated=? WHERE id=?',(revision,chat))
    return {'revision':revision}

def model_messages(chat,seq,context):
    """Select a bounded recent suffix. Old attachments are not sent again."""
    chat=ident(chat);seq=seqnum(seq)
    current=content(chat,seq)
    def cost(text):
        return len(text.encode('utf-8'))//2+32
    current_text=current if isinstance(current,str) else ' '.join(p.get('text','') for p in current if isinstance(p,dict))
    budget=max(0,int(context*.65)-cost(current_text))
    if isinstance(current,list):
        budget=max(0,budget-2048*sum(p.get('type')!='text' for p in current if isinstance(p,dict)))
    result=[]
    with connect() as db:
        # Lengths first, to avoid reading giant old code blocks unnecessarily.
        rows=db.execute("""SELECT seq,length(CAST(text AS BLOB)) + length(CAST(answer AS BLOB)) AS size
           FROM turns WHERE chat=? AND seq<? AND answer<>'' ORDER BY seq DESC LIMIT 64""",(chat,seq)).fetchall()
        for row in rows:
            if row['size']//2+64>budget: break
            t=db.execute('SELECT text,answer,files FROM turns WHERE chat=? AND seq=?',(chat,row['seq'])).fetchone()
            u=t['text']
            if json.loads(t['files']): u=(u+'\n[Earlier attachments omitted from model context.]').strip()
            n=cost(u)+cost(t['answer'])
            if n>budget: break
            budget-=n
            result.insert(0,[{'role':'user','content':u},{'role':'assistant','content':t['answer']}])
    return [m for pair in result for m in pair]+[{'role':'user','content':current}]

def user_text(chat,seq):
    with connect() as db:
        row=db.execute('SELECT text FROM turns WHERE chat=? AND seq=?',(ident(chat),seqnum(seq))).fetchone()
        return row[0] if row else ''

def store_image(chat,seq,png,prompt):
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO generated_images VALUES(?,?,?,?)',(ident(chat),seqnum(seq),png,prompt))

def generated_image(chat,seq):
    with connect() as db:
        row=db.execute('SELECT png FROM generated_images WHERE chat=? AND seq=?',(ident(chat),seqnum(seq))).fetchone()
        return row[0] if row else None

def start_shell(chat,seq,idx,command,cwd):
    with connect() as db:
        db.execute('INSERT INTO shell_runs(chat,seq,idx,command,cwd) VALUES(?,?,?,?,?)',(ident(chat),seqnum(seq),idx,command,cwd))

def finish_shell(chat,seq,idx,output,code,status):
    with connect() as db:
        db.execute('UPDATE shell_runs SET output=?,exit_code=?,status=? WHERE chat=? AND seq=? AND idx=?',(output,code,status,ident(chat),seqnum(seq),idx))
