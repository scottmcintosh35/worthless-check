"""Read-path indexes and cross-session invalidation without caching financial values."""
def change_marker(db):
    return db.total_changes,db.execute('PRAGMA data_version').fetchone()[0]

def setup(db):
    db.executescript('''CREATE INDEX IF NOT EXISTS perf_payments_case ON payments(case_id,voided);
      CREATE INDEX IF NOT EXISTS perf_adjustments_case ON adjustments(case_id);
      CREATE INDEX IF NOT EXISTS perf_defendants_name ON defendants(name,id);
      CREATE INDEX IF NOT EXISTS perf_aliases_owner ON defendant_aliases(defendant_id,name);''')
