"""Read-only source import. Preserves raw DBF/FPT files and all physical records."""
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
import struct


def fields_from(data):
    count, header, size = struct.unpack_from('<IHH',data,4)
    if header < 33 or header > len(data) or size < 1 or header+count*size > len(data):
        raise ValueError('Invalid or truncated DBF header/records')
    fields, pos = [], 1
    for offset in range(32,header,32):
        if data[offset] == 13:
            break
        desc = data[offset:offset+32]
        if len(desc)!=32:
            raise ValueError('Truncated field descriptor')
        name=desc[:11].split(b'\0')[0].decode('ascii')
        length=desc[16]
        fields.append({'name':name,'type':chr(desc[11]),'length':length,'decimals':desc[17],'offset':pos})
        pos+=length
    if pos != size:
        raise ValueError('Field widths do not match record size')
    return count,header,size,fields


def migrate(source, output, progress=None):
    source,output=Path(source).resolve(),Path(output).resolve()
    if output.exists():
        raise ValueError('Destination already exists. Choose a new file; existing databases are never overwritten.')
    if output.is_relative_to(source):
        raise ValueError('Destination must be outside the source backup folder.')
    paths=sorted(p for p in source.iterdir() if p.suffix.upper() in ('.DBF','.FPT') and p.is_file())
    if not any(p.suffix.upper()=='.DBF' for p in paths):
        raise ValueError('No DBF files found.')
    output.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(output)
    db.executescript('''
    CREATE TABLE import_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE source_files(name TEXT PRIMARY KEY,sha256 TEXT NOT NULL,bytes BLOB NOT NULL);
    CREATE TABLE source_tables(name TEXT PRIMARY KEY,fields_json TEXT NOT NULL,encoding TEXT NOT NULL,
      record_count INTEGER NOT NULL,active_count INTEGER NOT NULL,deleted_count INTEGER NOT NULL);
    CREATE TABLE legacy_records(table_name TEXT NOT NULL,record_no INTEGER NOT NULL,deleted INTEGER NOT NULL,
      data_json TEXT NOT NULL,raw_record BLOB NOT NULL,case_no TEXT,def_id TEXT,merchant_id TEXT,
      name TEXT,receipt_no TEXT,PRIMARY KEY(table_name,record_no));
    CREATE INDEX by_case ON legacy_records(table_name,case_no);
    CREATE INDEX by_def ON legacy_records(table_name,def_id);
    CREATE INDEX by_name ON legacy_records(table_name,name);
    CREATE TABLE legacy_memos(table_name TEXT NOT NULL,pointer INTEGER NOT NULL,
      kind INTEGER,raw BLOB,text TEXT,error TEXT,PRIMARY KEY(table_name,pointer));
    CREATE TABLE import_issues(table_name TEXT,record_no INTEGER,field TEXT,issue TEXT);
    ''')
    report={'tables':[],'files':[],'issues':{},'status':'incomplete','encoding_policy':'Driver 1 = cp437; unmarked driver 0 assumed cp1252. Raw bytes preserved.'}
    def notify(message):
        if progress is not None:
            progress(message)
    try:
        with db:
            for path in paths:
                notify('Preserving source file: '+path.name)
                data=path.read_bytes()
                digest=hashlib.sha256(data).hexdigest()
                db.execute('INSERT INTO source_files VALUES(?,?,?)',(path.name.upper(),digest,data))
                report['files'].append({'name':path.name.upper(),'bytes':len(data),'sha256':digest})
            lookup={p.name.upper():p for p in paths}
            for path in paths:
                if path.suffix.upper()!='.DBF':
                    continue
                table=path.stem.upper()
                notify('Importing table: '+table)
                data=db.execute('SELECT bytes FROM source_files WHERE name=?',(path.name.upper(),)).fetchone()[0]
                count,header,size,fields=fields_from(data)
                driver=data[29]
                encoding={0:'cp1252',1:'cp437',2:'cp850',3:'cp1252'}.get(driver)
                if encoding is None:
                    raise ValueError(f'Unsupported encoding driver {driver} in {table}')
                memo_name=table+'.FPT'
                memo=db.execute('SELECT bytes FROM source_files WHERE name=?',(memo_name,)).fetchone()
                memo=memo[0] if memo else b''
                block=int.from_bytes(memo[6:8],'big') if len(memo)>=8 else 0
                seen=set()
                active=deleted=0
                sums={}
                def issue(rec,field,reason):
                    db.execute('INSERT INTO import_issues VALUES(?,?,?,?)',(table,rec,field,reason))
                for index in range(count):
                    if index and index % 5000 == 0:
                        notify(f'Importing {table}: {index:,} of {count:,} records')
                    raw=data[header+index*size:header+(index+1)*size]
                    is_deleted=raw[0]==42
                    if raw[0] not in (32,42):
                        issue(index+1,'_deleted','Unknown record marker')
                    deleted+=int(is_deleted)
                    active+=int(not is_deleted)
                    values={}
                    for f in fields:
                        value=raw[f['offset']:f['offset']+f['length']]
                        typ=f['type']
                        if typ=='M':
                            try:
                                pointer=int(value.strip() or b'0')
                            except ValueError:
                                issue(index+1,f['name'],'Invalid memo pointer')
                                values[f['name']]={'memo_error':'Invalid pointer'}
                                continue
                            values[f['name']]={'memo':pointer}
                            if pointer and pointer not in seen:
                                seen.add(pointer)
                                start=pointer*block
                                error=None
                                kind=None
                                payload=b''
                                if not block or start<8 or start+8>len(memo):
                                    error='Memo pointer outside file or missing memo file'
                                else:
                                    kind,length=struct.unpack_from('>II',memo,start)
                                    if start+8+length>len(memo):
                                        error='Memo content truncated'
                                    else:
                                        payload=memo[start+8:start+8+length]
                                text=payload.decode(encoding,errors='replace') if kind==1 else None
                                db.execute('INSERT INTO legacy_memos VALUES(?,?,?,?,?,?)',(table,pointer,kind,payload,text,error))
                                if error:
                                    issue(index+1,f['name'],error)
                                elif kind!=1:
                                    issue(index+1,f['name'],'Non-text memo preserved as binary')
                        elif typ in ('C','N','F','D','L'):
                            text=value.decode(encoding,errors='replace').rstrip(' \0')
                            values[f['name']]=text.strip() if typ!='C' else text
                            if typ in ('N','F') and not is_deleted and text.strip():
                                try:
                                    amount=Decimal(text.strip())
                                    if not amount.is_finite():
                                        raise InvalidOperation
                                    sums[f['name']]=sums.get(f['name'],Decimal(0))+amount
                                except InvalidOperation:
                                    issue(index+1,f['name'],'Invalid numeric value retained as text')
                        else:
                            values[f['name']]={'raw_hex':value.hex()}
                            issue(index+1,f['name'],'Unsupported field type retained as raw bytes')
                    get=lambda k:str(values.get(k,''))
                    db.execute('INSERT INTO legacy_records VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (table,index+1,int(is_deleted),json.dumps(values,ensure_ascii=True),raw,get('CASE_NO'),get('DEF_ID') or get('ID') or get('AL_ID'),get('MERCH_ID') or get('ME_ID'),get('NAME') or get('DEFENDANT') or get('ME_NAME') or get('AL_NAME'),get('RECEIPT_NO')))
                db.execute('INSERT INTO source_tables VALUES(?,?,?,?,?,?)',(table,json.dumps(fields),encoding,count,active,deleted))
                actual=db.execute('SELECT COUNT(*),SUM(deleted) FROM legacy_records WHERE table_name=?',(table,)).fetchone()
                if actual[0]!=count or (actual[1] or 0)!=deleted:
                    raise ValueError('Imported record count mismatch')
                report['tables'].append({'table':table,'records':count,'active':active,'deleted':deleted,'encoding':encoding,
                    'active_numeric_totals':{k:str(v) for k,v in sums.items()}})
            for reason,total in db.execute('SELECT issue,COUNT(*) FROM import_issues GROUP BY issue'):
                report['issues'][reason]=total
            for path in paths:
                notify('Verifying source file: '+path.name)
                digest=hashlib.sha256(path.read_bytes()).hexdigest()
                stored=db.execute('SELECT sha256 FROM source_files WHERE name=?',(path.name.upper(),)).fetchone()[0]
                if digest!=stored:
                    raise ValueError('A source file changed during import; destination is not valid.')
            report['status']='imported_for_read_only_review'
            report['record_total']=sum(t['records'] for t in report['tables'])
            db.execute('INSERT INTO import_meta VALUES(?,?)',('report',json.dumps(report)))
        notify('Checking destination database integrity')
        integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity!='ok':
            raise ValueError('SQLite integrity check failed')
        db.close()
        output.with_suffix('.report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        return report
    except Exception:
        db.close()
        # Leave failed output for diagnosis; no successful metadata means viewer refuses it.
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    report=migrate(args.source,args.output)
    print(json.dumps({'tables':len(report['tables']),'records':report['record_total'],'issues':report['issues'],'status':report['status']}))
