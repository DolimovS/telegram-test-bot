import json
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=5), 'Asia/Tashkent')
NAV = [[{'text': '📚 Mening tarixim', 'callback_data': 'history'},
        {'text': '🏠 Bosh menyu', 'callback_data': 'menu'}]]

def stamp(value):
    return datetime.fromtimestamp(value, TZ).strftime('%d.%m.%Y · %H:%M')

def choices(answers, wrong=None):
    return '\n'.join(f'{i}. {letter}' + ('' if wrong is None else (' ❌' if i in wrong else ' ✅'))
                     for i, letter in enumerate(answers, 1))

def render(r):
    visible = r['score'] is not None
    heading = '📊 TEST NATIJASI' if visible else '🔒 NATIJA KUTILMOQDA'
    lines = [heading, f"Test kodi: {r['code']}", f"👤 Telegram ID: {r['uid']}",
             f"🗓 {stamp(r['submitted'])} (Toshkent)", '']
    if visible:
        total = len(r['answers'])
        lines += [f"🏆 Ball: {r['score']} / {total} · {r['score'] / total * 100:.1f}%",
                  f"To‘g‘ri: {r['score']}   |   Xato: {total-r['score']}", '',
                  'SIZNING JAVOBLARINGIZ', choices(r['answers'], set(json.loads(r['wrong'])))]
    else:
        lines += ['Javoblaringiz saqlandi. Natija test yopilganda ochiladi.', '',
                  'SIZNING JAVOBLARINGIZ', choices(r['answers'])]
    return '\n'.join(lines)

def preview(code, answers):
    return f'📝 JAVOBLARNI TEKSHIRING\nTest kodi: {code}\nSavollar: {len(answers)} ta\n\n' + choices(answers) + '\n\nYakuniy topshirishni tasdiqlaysizmi?\nTasdiqlangach, javoblarni o‘zgartirib bo‘lmaydi.'

def chunks(text, limit=3500):
    """Keep lines intact where possible, counting Telegram UTF-16 units."""
    current = ''
    size = 0
    for line in text.splitlines(keepends=True):
        units = len(line.encode('utf-16-le')) // 2
        if current and size + units > limit:
            yield current
            current, size = '', 0
        if units <= limit:
            current += line
            size += units
        else:
            for char in line:
                n = 2 if ord(char) > 65535 else 1
                if size + n > limit:
                    yield current
                    current, size = '', 0
                current += char
                size += n
    if current:
        yield current
