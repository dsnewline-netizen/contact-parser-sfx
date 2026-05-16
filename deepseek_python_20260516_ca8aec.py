# app.py
import re, requests, os, sys
from flask import Flask, request, jsonify, render_template_string

# Попытка загрузить .env (если есть)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
DGIS_API_KEY = os.environ.get("DGIS_API_KEY", "")
DGIS_BASE_URL = "https://catalog.api.2gis.com/3.0/items"

def extract_emails(text):
    return set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text))

def extract_phones(text):
    patterns = [
        r'\+7\s?\(?\d{3}\)?\s?\d{3}[\s-]?\d{2}[\s-]?\d{2}',
        r'8\s?\(?\d{3}\)?\s?\d{3}[\s-]?\d{2}[\s-]?\d{2}',
        r'\+7\d{10}',
        r'8\d{10}'
    ]
    phones = set()
    for pattern in patterns:
        phones.update(re.findall(pattern, text))
    normalized = set()
    for p in phones:
        digits = re.sub(r'\D', '', p)
        if len(digits) == 11 and digits[0] == '8':
            digits = '+7' + digits[1:]
        elif len(digits) == 10:
            digits = '+7' + digits
        if digits.startswith('+7') and len(digits) == 12:
            normalized.add(digits)
    return normalized

def get_city_id(city_name):
    params = {
        'q': city_name,
        'type': 'adm_div.city',
        'key': DGIS_API_KEY,
        'fields': 'items.id,items.name'
    }
    try:
        resp = requests.get(DGIS_BASE_URL, params=params, timeout=10)
        data = resp.json()
        if data.get('meta', {}).get('code') == 200 and data.get('result', {}).get('items'):
            return data['result']['items'][0]['id']
    except Exception:
        pass
    return None

def search_2gis(city, business):
    if not DGIS_API_KEY:
        return [], ["API-ключ не задан. Создайте файл .env с DGIS_API_KEY=ваш_ключ"]
    city_id = get_city_id(city)
    if not city_id:
        return [], ["Город не найден"]
    params = {
        'q': f"{business} {city}",
        'city_id': city_id,
        'type': 'branch',
        'page_size': 10,
        'key': DGIS_API_KEY,
        'fields': 'items.name,items.address_name,items.point'
    }
    try:
        resp = requests.get(DGIS_BASE_URL, params=params, timeout=10)
        data = resp.json()
        if data.get('meta', {}).get('code') != 200:
            return [], ["Ошибка API 2GIS"]
        items = data.get('result', {}).get('items', [])
        emails, phones = set(), set()
        for item in items:
            text = f"{item.get('name', '')} {item.get('address_name', '')}"
            emails.update(extract_emails(text))
            phones.update(extract_phones(text))
        return emails, phones
    except Exception:
        return [], ["Ошибка запроса к 2GIS"]

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head><title>Парсер контактов</title><meta charset="utf-8"></head>
<body>
    <h2>Поиск через 2ГИС</h2>
    <form action="/search">
        Город: <input name="city" required><br><br>
        Направление: <input name="business" required><br><br>
        <button type="submit">Искать</button>
    </form>
    {% if results %}
        <h3>Результаты для "{{ query }}"</h3>
        <h4>Email:</h4>
        <ul>
        {% for e in results.emails %}<li>{{ e }}</li>{% else %}<li>Не найдено</li>{% endfor %}
        </ul>
        <h4>Телефоны:</h4>
        <ul>
        {% for p in results.phones %}<li>{{ p }}</li>{% else %}<li>Не найдено</li>{% endfor %}
        </ul>
    {% endif %}
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, results=None)

@app.route('/search')
def search():
    city = request.args.get('city', '').strip()
    business = request.args.get('business', '').strip()
    if not city or not business:
        return jsonify({'error': 'city и business обязательны'}), 400
    emails, phones = search_2gis(city, business)
    if isinstance(phones, list) and phones and phones[0].startswith('API'):
        return jsonify({'error': phones[0]}), 500
    results = {
        'query': f"{business} в {city}",
        'emails': sorted(list(emails)),
        'phones': sorted(list(phones))
    }
    if request.headers.get('Accept') == 'application/json':
        return jsonify(results)
    return render_template_string(HTML_TEMPLATE, results=results, query=results['query'])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)