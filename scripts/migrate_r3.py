#!/usr/bin/env python3
"""One-off, idempotent migration for rule r3 (2026-10-25): widen the CHECK constraints on evidence.claim
('audience_rating_count') and flags.flag_type ('audience_count_unreadable') in an existing movies.db, then re-apply schema.sql
(new audience_count_obs table and r3 views). Fresh databases get the new constraints straight from schema.sql."""
import os, re, sqlite3
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
c=sqlite3.connect(os.path.join(BASE,'movies.db'))
schema=open(os.path.join(BASE,'schema.sql')).read()
c.execute('PRAGMA foreign_keys=OFF'); c.execute('PRAGMA legacy_alter_table=ON')
for tbl,needle in (('evidence','audience_rating_count'),('flags','audience_count_unreadable')):
    cur=c.execute("select sql from sqlite_master where type='table' and name=?",(tbl,)).fetchone()[0]
    if needle in cur: print(tbl,'already migrated'); continue
    ddl=re.search(r'CREATE TABLE IF NOT EXISTS %s\(.*?\);'%tbl,schema,re.S).group(0)
    n=c.execute(f'select count(*) from {tbl}').fetchone()[0]
    c.execute(f'ALTER TABLE {tbl} RENAME TO {tbl}_old'); c.execute(ddl)
    cols=','.join(r[1] for r in c.execute(f'PRAGMA table_info({tbl}_old)'))
    c.execute(f'INSERT INTO {tbl}({cols}) SELECT {cols} FROM {tbl}_old'); c.execute(f'DROP TABLE {tbl}_old')
    assert c.execute(f'select count(*) from {tbl}').fetchone()[0]==n; print(tbl,'migrated',n,'rows')
c.commit(); c.execute('PRAGMA foreign_keys=ON'); c.executescript(schema); c.commit()
print(c.execute('PRAGMA integrity_check').fetchone(), c.execute('PRAGMA foreign_key_check').fetchall())
