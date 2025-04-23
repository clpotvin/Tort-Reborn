import requests
from flask import Flask, request

from Helpers.database import DB

app = Flask(__name__)


@app.route('/application', methods=['POST'])
def webhook():
    if request.method == 'POST':
        json_data = request.json
        data = {'username': 'Tort', 'embeds': []}
        embed = {'fields': [], 'title': json_data['data']['fields'][1]['value']}
        for field in json_data['data']['fields']:
            fld = {}
            if field['label'] == 'ticket':
                ticket = field['value']
                continue
            elif field['label'] == 'Timezone':
                fld['name'] = field['label']
                fld['value'] = lambda x: (x for x in field['options'] if x['id'] == field['value'])['text']
                continue
            elif field['value'] is None:
                continue
            fld['name'] = field['label']
            fld['value'] = field['value']
            embed['fields'].append(fld)
        data['embeds'].append(embed)

        db = DB()
        db.connect()

        db.cursor.execute(f'SELECT * FROM new_app WHERE channel = \'{ticket}\'')
        result = db.cursor.fetchone()
        if result:
            url = result[0][3]
            requests.post(url, json=data, headers={"Content-Type": "application/json"})
        return "Data received"


app.run(host='0.0.0.0', port=8001)
