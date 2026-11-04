import socket
import subprocess
import time
import requests
from flask import Flask, request
from subprocess import Popen
import logging
import psutil

app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
SERVER = "http://localhost:5000/ingest"
THREADS = psutil.cpu_count()
NUMS_PER_THREAD = 5000

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

IP = 'localhost'
PORT = 5001

@app.route("/", methods=['POST'])
def ingest():
    data = request.json
    nums = data['nums']
    session_id = data['session_id']
    processes = []
    for i in range(THREADS):
        num_segments = ["./calculate-prime"]
        for j in range(NUMS_PER_THREAD):
            num_segments.append(str(nums[i * NUMS_PER_THREAD + j]))
        processes.append(Popen(num_segments, stdout=subprocess.PIPE))
    results = []
    for i, process in enumerate(processes):
        outputs = process.communicate()[0].decode('utf-8').split('\n')
        results.extend([int(o) for o in outputs if o])
    payload = {"ip": IP, "port": PORT, "threads": THREADS * NUMS_PER_THREAD, "empty": False, "results": results, "session_id": session_id, "packet_id": data["packet_id"]}
    while True:
        try:
            requests.post(SERVER, json=payload, timeout=0.1)
            break;
        except requests.exceptions.ReadTimeout:
            break
        except Exception:
            time.sleep(10)
    return "OK", 200

if __name__ == '__main__':
    payload = {"ip": IP, "port": PORT, "threads": THREADS * NUMS_PER_THREAD, "empty": True, "session_id": 0}
    while True:
        try:
            requests.post(SERVER, json=payload, timeout=0.1)
            break
        except requests.exceptions.ReadTimeout:
            break
        except Exception:
            time.sleep(10)
    app.run(host='0.0.0.0', port=PORT, debug=False)
