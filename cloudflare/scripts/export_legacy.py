"""Export a consistent read-only snapshot for import into an EMPTY D1 database."""
import argparse
import sqlite3
from pathlib import Path

TABLES = {
    'tests': ('code', 'key', 'delayed', 'deadline', 'closed', 'archived'),
    'attempts': ('code', 'uid', 'answers', 'submitted', 'score', 'wrong', 'notified'),
}

def export(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise ValueError('Manba baza topilmadi.')
    if destination.exists():
        raise ValueError('Chiqish fayli mavjud. Yangi fayl nomini tanlang.')
    connection = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    counts = {}
    try:
        connection.execute('BEGIN')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('x', encoding='utf-8', newline='\n') as out:
            out.write('-- PRIVATE: answer keys and student history. Never commit this file.\n')
            for table, columns in TABLES.items():
                count = 0
                for row in connection.execute(f'SELECT {",".join(columns)} FROM {table}'):
                    values = ','.join(connection.execute('SELECT quote(?)', (value,)).fetchone()[0] for value in row)
                    out.write(f'INSERT INTO {table}({",".join(columns)}) VALUES({values});\n')
                    count += 1
                counts[table] = count
            try:
                retired = list(connection.execute('SELECT code FROM retired_codes'))
            except sqlite3.OperationalError:
                retired = []
            for (code,) in retired:
                value = connection.execute('SELECT quote(?)', (code,)).fetchone()[0]
                out.write(f'INSERT INTO retired_codes(code) VALUES({value});\n')
            out.write('DELETE FROM available_codes WHERE code IN (SELECT code FROM tests);\n')
        connection.rollback()
    finally:
        connection.close()
    return counts

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default='../bot.sqlite3')
    parser.add_argument('--out', default='.private/legacy-data.sql')
    args = parser.parse_args()
    try:
        counts = export(args.db, args.out)
    except (ValueError, sqlite3.Error, OSError) as error:
        raise SystemExit('Eksport bajarilmadi: ' + type(error).__name__)
    print(f"Eksport tayyor: {counts['tests']} test, {counts['attempts']} topshirish. Fayl maxfiy saqlansin.")
