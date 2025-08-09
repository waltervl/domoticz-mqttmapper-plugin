import threading
import queue
import random
import string
import json
import os

from flask import Flask, render_template, Response, send_from_directory
import paho.mqtt.client as mqtt

app = Flask(__name__)

clients = []
retained_messages = {}
BROKER_HOST = '192.168.1.101'
BROKER_PORT = 1883
TOPIC = '#'

def generate_client_id():
    suffix = ''.join(random.choices(string.hexdigits, k=8))
    return 'anon_' + suffix

def on_connect(client, userdata, flags, rc):
    print(f'[MQTT] Connected (rc={rc})')
    client.subscribe(TOPIC)

def on_message(client, userdata, msg):
    topic = msg.topic
    raw = msg.payload.decode(errors='ignore')
    # Flatten payload: alle nieuwe regels naar spatie, dubbele spaties samenvoegen
    payload = ' '.join(raw.split())
    # Sla retained op
    if msg.retain:
        retained_messages[topic] = payload

    # Bouw JSON-string éénregel
    packet = json.dumps({
        "topic":   topic,
        "payload": payload
    })
    # Stuurt één event per JSON
    for q in list(clients):
        q.put(packet)

def mqtt_thread():
    client = mqtt.Client(client_id=generate_client_id(), clean_session=True)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_forever()

proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

app = Flask(
    __name__,
    static_folder='static',            # behoud je webgui/static
    static_url_path='/static'
)

# Extra statics uit parent-folder
@app.route('/assets/<path:filename>')
def project_assets(filename):
    return send_from_directory(proj_root, filename)
    
@app.route('/')
def index():
    return render_template('index.html',
        broker_host=BROKER_HOST,
        broker_port=BROKER_PORT)

@app.route('/events')
def sse_stream():
    def stream():
        q = queue.Queue()
        clients.append(q)
        # bij connect bestaande retained doorsturen
        for t, p in retained_messages.items():
            q.put(json.dumps({"topic":t, "payload":p}))
        try:
            while True:
                msg = q.get()
                yield f'data: {msg}\n\n'
        except GeneratorExit:
            clients.remove(q)

    return Response(stream(), mimetype='text/event-stream')

if __name__ == '__main__':
    threading.Thread(target=mqtt_thread, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=True)
