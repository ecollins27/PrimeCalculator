import math
import re
import random
from tarfile import data_filter

from flask import Flask, render_template, request, jsonify
import os
import mariadb
from flask_socketio import SocketIO
import threading
import logging
import psutil
from pathlib import Path
import shutil
import time
import subprocess
from subprocess import Popen

RESET_DATABASE = True
OFFSET = 250000
USERNAME = "username"
PASSWORD = "password"
PARTITION_SIZE = 1000000000
MAX_PARTITION_VALUE = PARTITION_SIZE
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
THREADS = psutil.cpu_count()
NUMS_PER_THREAD = 5000

app = Flask(__name__)
socketio = SocketIO(app)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

next_check = ""
increment_index = 1
num_primes = 0


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
    num_primes = len(primes)
    return size, possible_primes, increments

initial_primes = [2, 3, 5, 7, 11, 13, 17, 19, 23]
# initial_primes = [2, 3, 5]
cycle_size, prime_cycle, increments = calculate_cycle(initial_primes)


def exists(cursor, num):
    cursor.execute(f"SELECT COUNT(*) FROM primes WHERE number = {num}")
    return int(cursor.fetchone()[0]) > 0

def reset_database():
    global SESSION_ID
    database = mariadb.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
    cursor = database.cursor()
    cursor.execute("DROP TABLE primes")
    cursor.execute(f"CREATE TABLE primes (number BIGINT UNSIGNED, id BIGINT UNSIGNED AUTO_INCREMENT, PRIMARY KEY (id), INDEX (number)) PARTITION BY RANGE(id) (PARTITION p0 VALUES LESS THAN ({PARTITION_SIZE}))")
    cursor.execute("TRUNCATE TABLE index_lookup")
    primes = [f"({prime})" for prime in initial_primes]
    cursor.execute(f"INSERT IGNORE INTO primes (number) VALUE {','.join(primes)}")
    cursor.execute(f"INSERT INTO index_lookup VALUE (0, 2)")
    database.commit()
    database.close()
    SESSION_ID += 1
    with open('session.txt', 'w') as f:
        f.write(str(SESSION_ID))

@app.route("/api/index-generate")
def generate_by_index():
    try:
        pass
    except Exception as e:
        pass
    finally:
        os.remove('index-generate.lock')

@app.route("/api/num_check", methods=['GET'])
def check_num():
    try:
        num = int(request.args.get("num"))
        database = mariadb.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
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
            database = mariadb.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
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
        database = mariadb.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
        cursor = database.cursor()
        packet = {"random": format(get_prime_at_index(index, cursor))}
        database.close()
    except Exception:
        packet = {"random": ""}
    return jsonify(packet)

@app.route("/", methods=["GET"])
def get_prime_html():
    return render_template("prime.html", num_primes=format(num_primes), max_num=format(next_check))

def calculate_primes():
    global next_check
    global increments
    global increment_index
    global num_primes
    database = mariadb.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
    cursor = database.cursor()
    while True:
        processes = []
        for i in range(THREADS):
            num_segments = ["./calculate-prime"]
            for j in range(NUMS_PER_THREAD):
                num_segments.append(str(next_check))
                next_check += increments[increment_index]
                increment_index = (increment_index + 1) % len(increments)
            processes.append(Popen(num_segments, stdout=subprocess.PIPE))
        for i, process in enumerate(processes):
            outputs = process.communicate()[0].decode('utf-8').split('\n')
            for i in range(0, len(outputs), 1000):
                cursor.executemany("INSERT IGNORE INTO primes (number) VALUE (%s)", [(p,) for p in outputs[i:(i + 1000)]])
            num_primes += len(outputs)
        database.commit()

def emit_updates():
    global num_primes
    global MAX_PARTITION_VALUE
    while True:
        database = mariadb.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
        cursor = database.cursor()
        cursor.execute("SELECT * FROM index_lookup ORDER BY row DESC LIMIT 1")
        row, prime = cursor.fetchone()
        row, prime = int(row), int(prime)
        cursor.execute(f"SELECT COUNT(*) FROM primes WHERE number > {prime}")
        for i in range(row + OFFSET, num_primes, OFFSET):
            command = f"SELECT * FROM primes WHERE number >= {prime} ORDER BY number ASC LIMIT 1 OFFSET {OFFSET}"
            cursor.execute(command)
            new_prime = cursor.fetchone()
            if new_prime:
                new_prime = int(new_prime[0])
                cursor.execute(f"INSERT IGNORE INTO index_lookup VALUE ({i},{new_prime})")
                prime = new_prime
                cursor = database.cursor()
        partition_num = num_primes // PARTITION_SIZE
        if (partition_num + 2) * PARTITION_SIZE > MAX_PARTITION_VALUE:
            cursor.execute(f"ALTER TABLE primes ADD PARTITION (PARTITION p{partition_num + 1} VALUES LESS THAN ({(partition_num + 2) * PARTITION_SIZE}))")
            MAX_PARTITION_VALUE = (partition_num + 2) * PARTITION_SIZE
        database.commit()
        database.close()
        socketio.emit("count_update", {'count': format(num_primes), 'max':format(next_check)})


if __name__ == '__main__':
    if RESET_DATABASE:
        reset_database()
    else:
        database = mariadb.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
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
    thread1 = threading.Thread(target=emit_updates)
    thread2 = threading.Thread(target=calculate_primes)
    thread1.start()
    thread2.start()
    app.run(host='0.0.0.0', port=5000,debug=False)
