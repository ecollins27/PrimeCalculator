import math
import re
import random
from flask import Flask, render_template, request, jsonify
import os
import mysql.connector
import requests
import time
from flask_socketio import SocketIO
import threading
import logging
from pathlib import Path
import shutil
import subprocess

RESET_DATABASE = True
OFFSET = 250000
USERNAME = "username"
PASSWORD = "password"
PARTITION_SIZE = 1000000000
MAX_PARTITION_VALUE = PARTITION_SIZE
BY_INDEX_SPLIT = [(1000000000, 'billion'), (1000000, 'million')]
BY_RANGE_SPLIT = [(1000000000000, 'trillion'), (1000000000, 'billion'), (1000000, 'million')]
with open('session.txt', 'r') as f:
    SESSION_ID = int(f.read())
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
socketio = SocketIO(app)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

next_check = ""
next_check_lock = threading.Lock()
increment_index = 1
increment_index_lock = threading.Lock()
num_primes = 0
num_primes_lock = threading.Lock()
packets = set()
packets_lock = threading.Lock()
packet_id = 0
packet_id_lock = threading.Lock()


def format(num):
    pattern = r"(?m)(?<=\d)\d{3}(?=(?:\d{3})*$)"
    return str(re.sub(pattern, r",\g<0>", str(num)))

def calculate_cycle(primes):
    global next_check
    global num_primes
    size = 1
    for prime in primes:
        size = math.lcm(size, prime)
    print(f"Creating {size} cycle")
    increments = []
    possible_primes = [1]
    prev = 1
    for i in range(3, size, 2):
        prob_prime = True
        for prime in primes:
            if i % prime == 0:
                prob_prime = False
                break
        if prob_prime:
            possible_primes.append(i)
            increments.append(i - prev)
            prev = i
    increments.append(1 + size - prev)
    print(f"Checking {100 * len(increments) / size}% of all numbers")
    next_check = 1 + increments[0]
    with num_primes_lock:
        num_primes = len(primes)
    return size, possible_primes, increments

def get_num_primes(cursor):
    cursor.execute("SHOW TABLE STATUS LIKE 'primes'")
    num_primes = int(cursor.fetchone()[4])
    return num_primes

initial_primes = [2, 3, 5, 7, 11, 13, 17, 19, 23]
# initial_primes = [2, 3, 5]
cycle_size, prime_cycle, increments = calculate_cycle(initial_primes)


def exists(cursor, num):
    cursor.execute(f"SELECT COUNT(*) FROM primes WHERE number = {num}")
    return int(cursor.fetchone()[0]) > 0

def reset_database():
    global SESSION_ID
    database = mysql.connector.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
    cursor = database.cursor()
    cursor.execute("DROP TABLE primes")
    cursor.execute(f"CREATE TABLE primes (number BIGINT UNSIGNED, id BIGINT UNSIGNED AUTO_INCREMENT, PRIMARY KEY (id)) PARTITION BY RANGE(id) (PARTITION p0 VALUES LESS THAN ({PARTITION_SIZE}))")
    cursor.execute("TRUNCATE TABLE index_lookup")
    for item in os.listdir(f"{BASE_DIR}/browse"):
        abs_path = f"{BASE_DIR}/browse/{item}"
        if os.path.isfile(abs_path):
            os.remove(abs_path)
        else:
            shutil.rmtree(abs_path)
    primes = [f"({prime})" for prime in initial_primes]
    cursor.execute(f"INSERT IGNORE INTO primes (number) VALUE {','.join(primes)}")
    cursor.execute(f"INSERT INTO index_lookup VALUE (0, 2)")
    database.commit()
    database.close()
    SESSION_ID += 1
    with open('session.txt', 'w') as f:
        f.write(str(SESSION_ID))

@app.route("/ingest", methods=["POST"])
def ingest():
    global next_check
    global increments
    global increment_index
    global num_primes
    global packets
    global packet_id
    data = request.json
    ip = data['ip']
    port = data['port']
    num_nums = data['threads']
    if not data['empty'] and SESSION_ID == data['session_id']:
        with packets_lock:
            packets.remove(data['packet_id'])
        results = data['results']
        database = mysql.connector.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
        cursor = database.cursor()
        for i in range(0, len(results), 1000):
            cursor.executemany("INSERT IGNORE INTO primes (number) VALUE (%s)", [(p,) for p in results[i:(i + 1000)]])
        database.commit()
        database.close()
    elif data['empty']:
        time.sleep(5)
    next_nums = []
    for thread in range(num_nums):
        with next_check_lock, increment_index_lock:
            next_nums.append(next_check)
            next_check += increments[increment_index]
            increment_index = (increment_index + 1) % len(increments)
    with packet_id_lock, packets_lock:
        payload = {"nums": next_nums, 'session_id': SESSION_ID, 'packet_id': packet_id}
        packets.add(packet_id)
        packet_id += 1
    try:
        requests.post(f"http://{ip}:{port}", json=payload, timeout=2)
    finally:
        return "OK", 200

@app.route("/api/num_check", methods=['GET'])
def check_num():
    try:
        num = int(request.args.get("num"))
        database = mysql.connector.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
        cursor = database.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM primes WHERE number = '{num}'")
        if int(cursor.fetchone()[0]) > 0:
            return "OK", 200
        elif int(num) >= next_check:
            return "OK", 202
        else:
            return "OK", 201
    except Exception as e:
        return f"{e}", 404

def get_prime_at_index(index, cursor):
    rounded_index = index - (index % OFFSET)
    cursor.execute(f"SELECT * FROM index_lookup WHERE row = {rounded_index}")
    prime = int(cursor.fetchone()[1])
    cursor.execute(f"SELECT * FROM primes WHERE number >= {prime} ORDER BY number ASC LIMIT 1 OFFSET {index - rounded_index}")
    return int(cursor.fetchone()[0])

@app.route("/api/index", methods=['GET'])
def get_prime():
    try:
        index = int(request.args.get("num"))
        if index == 0:
            packet = {"prime": "Zero"}
        elif index > num_primes:
            packet = {"prime": "Unknown"}
        else:
            database = mysql.connector.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
            cursor = database.cursor()
            packet = {"prime": format(get_prime_at_index(index - 1, cursor)), "index": format(index)}
    except Exception as e:
        packet = {"prime": "Unknown"}
        print(e)
    return jsonify(packet)

@app.route("/api/random", methods=['GET'])
def get_random():
    try:
        index = random.randint(0, num_primes - 1)
        database = mysql.connector.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
        cursor = database.cursor()
        packet = {"random": format(get_prime_at_index(index, cursor))}
        database.close()
    except Exception:
        packet = {"random": ""}
    return jsonify(packet)

@app.route("/", methods=["GET"])
def get_prime_html():
    try:
        database = mysql.connector.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
        cursor = database.cursor()
        return render_template("prime.html", num_primes=format(num_primes), max_num=format(next_check))
    finally:
        database.close()

def create_by_index_file(cursor, starting_index):
    file_size = BY_INDEX_SPLIT[-1][0]
    file_loc = ""
    cp = starting_index
    for split in BY_INDEX_SPLIT:
        index = str(cp // split[0])
        indexp1 = str(int(index) + 1)
        while len(index) < 3:
            index = f"0{index}"
        while len(indexp1) < 3:
            indexp1 = f"0{indexp1}"
        file_loc += f"{index}-{indexp1}_{split[1]}/"
        cp = cp % split[0]
    file_loc = f"{file_loc[:-1]}.txt"
    file = Path( f"{BASE_DIR}/browse/by-index/{file_loc}")
    file.parent.mkdir(parents=True, exist_ok=True)

    cursor.execute(f"SELECT * FROM index_lookup WHERE row = {starting_index}")
    starting_prime = int(cursor.fetchone()[1])
    with file.open('w') as f:
        cursor.execute(f"SELECT * FROM primes WHERE number >= {starting_prime} ORDER BY number ASC LIMIT {file_size}")
        outputs = [str(line[0]) for line in cursor.fetchmany(file_size)]
        f.write('\n'.join(outputs))
    file_split = file_loc.split('/')[:-1]
    for i in range(len(file_split) - 1, -1, -1):
        dir = '/'.join(file_split[:(i + 1)])
        parent = '/'.join(file_split[:i])
        if len(os.listdir(f"{BASE_DIR}/browse/by-index/{dir}")) == BY_INDEX_SPLIT[i][0] // BY_INDEX_SPLIT[i + 1][0]:
            subprocess.run(f"cd {BASE_DIR}/browse/by-index/{parent} && zip -r {file_split[i]}.zip {file_split[i]}", shell=True)

def create_by_range_file(cursor, starting_num):
    file_range = BY_RANGE_SPLIT[-1][0]
    file_loc = ""
    cp = starting_num
    for split in BY_RANGE_SPLIT:
        index = str(cp // split[0])
        indexp1 = str(int(index) + 1)
        while len(index) < 3:
            index = f"0{index}"
        while len(indexp1) < 3:
            indexp1 = f"0{indexp1}"
        file_loc += f"{index}-{indexp1}_{split[1]}/"
        cp = cp % split[0]
    file_loc = f"{file_loc[:-1]}.txt"
    file = Path(f"{BASE_DIR}/browse/by-range/{file_loc}")
    file.parent.mkdir(parents=True, exist_ok=True)

    cursor.execute(f"SELECT COUNT(*) FROM primes WHERE number >= {starting_num} AND number < {starting_num + file_range} ORDER BY number ASC")
    count = int(cursor.fetchone()[0])
    with file.open('w') as f:
        cursor.execute(f"SELECT * FROM primes WHERE number >= {starting_num} AND number < {starting_num + file_range} ORDER BY number ASC")
        outputs = [str(line[0]) for line in cursor.fetchmany(count)]
        f.write('\n'.join(outputs))
    file_split = file_loc.split('/')[:-1]
    for i in range(len(file_split) - 1, -1, -1):
        dir = '/'.join(file_split[:(i + 1)])
        parent = '/'.join(file_split[:i])
        if len(os.listdir(f"{BASE_DIR}/browse/by-range/{dir}")) == BY_RANGE_SPLIT[i][0] // BY_RANGE_SPLIT[i + 1][0]:
            subprocess.run(f"cd {BASE_DIR}/browse/by-range/{parent} && zip -r {file_split[i]}.zip {file_split[i]}", shell=True)

def emit_updates():
    global num_primes
    global MAX_PARTITION_VALUE
    while True:
        database = mysql.connector.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
        cursor = database.cursor()
        cursor.execute("SELECT * FROM index_lookup ORDER BY row DESC LIMIT 1")
        row, prime = cursor.fetchone()
        row, prime = int(row), int(prime)
        cursor.execute(f"SELECT COUNT(*) FROM primes WHERE number > {prime}")
        num_primes = row + int(cursor.fetchone()[0]) + 1
        for i in range(row + OFFSET, num_primes, OFFSET):
            command = f"SELECT * FROM primes WHERE number >= {prime} ORDER BY number ASC LIMIT 1 OFFSET {OFFSET}"
            log.error(f"Command: '{command}'")
            cursor.execute(command)
            new_prime = int(cursor.fetchone()[0])
            log.error(f"Result: '{new_prime}'")
            cursor.execute(f"INSERT IGNORE INTO index_lookup VALUE ({i},{new_prime})")
            print(f"{new_prime // BY_RANGE_SPLIT[-1][0]} {prime // BY_RANGE_SPLIT[-1][0]}")
            if i % BY_INDEX_SPLIT[-1][0] == 0:
                pass
#                create_by_index_file(cursor, i - BY_INDEX_SPLIT[-1][0])
            if (new_prime // BY_RANGE_SPLIT[-1][0]) != (prime // BY_RANGE_SPLIT[-1][0]):
                lower = prime // BY_RANGE_SPLIT[-1][0]
                upper = new_prime // BY_RANGE_SPLIT[-1][0]
                for i in range(lower, upper):
                    pass
#                    create_by_range_file(cursor, i * BY_RANGE_SPLIT[-1][0])
            prime = new_prime
            cursor = database.cursor()
        partition_num = num_primes // PARTITION_SIZE
        if (partition_num + 2) * PARTITION_SIZE > MAX_PARTITION_VALUE:
            cursor.execute(f"ALTER TABLE primes ADD PARTITION (PARTITION p{partition_num + 1} VALUES LESS THAN ({(partition_num + 2) * PARTITION_SIZE}))")
            MAX_PARTITION_VALUE = (partition_num + 2) * PARTITION_SIZE
        database.commit()
        database.close()
        socketio.emit("count_update", {'count': format(num_primes), 'max':format(next_check), 'packets': str(packets)})


if __name__ == '__main__':
    log.error("here")
    if RESET_DATABASE:
        reset_database()
    else:
        database = mysql.connector.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
        cursor = database.cursor()
        cursor.execute("SELECT * FROM index_lookup ORDER BY row DESC LIMIT 1")
        latest_checkpoint, checkpoint_prime = cursor.fetchone()
        latest_checkpoint, checpoint_prime = int(latest_checkpoint), int(checkpoint_prime)
        cursor.execute(f"SELECT COUNT(*) FROM primes WHERE number > {checkpoint_prime}")
        num_primes = latest_checkpoint + int(cursor.fetchone()[0]) + 1
        cursor.execute("SELECT * FROM primes ORDER BY number DESC LIMIT 1")
        next_check = int(cursor.fetchone()[0])
        increment_index = prime_cycle.index(next_check % cycle_size)
        next_check += increments[increment_index]
        increment_index = (increment_index + 1) % len(increments)
    threading.Thread(daemon=True).start()
    thread = threading.Thread(target=emit_updates)
    thread.start()
    app.run(host='0.0.0.0', port=5000,debug=False)
