import math
import re
import random
from tarfile import data_filter
from flask import Flask, render_template, request, jsonify, send_file
import os
import mariadb
from flask_socketio import SocketIO
import threading
import logging
import psutil
from pathlib import Path
import shutil
import time
from datetime import datetime
import subprocess
from natsort import natsorted
from subprocess import Popen

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESET_DATABASE = True
CHUNK_SIZE = 250000
USERNAME = "user"
PASSWORD = "password"

app = Flask(__name__)
socketio = SocketIO(app)

num_primes = 0
max_prime = 0
db_size = 0
bits_per_prime = 0

def leading_zeros(str):
    for i, char in enumerate(str):
        if char != '0':
            return i
    return -1

def pad(str):
    return ("0" * (8 - len(str))) + str

class Decoder:

    bytes: list
    binary_str: str

    def __init__(self, filename):
        with open(filename, 'rb') as f:
            self.bytes = f.read()
        self.binary_str = ""

    def next_unary(self):
        bit_length = leading_zeros(self.binary_str)
        while len(self.bytes) > 0 and (bit_length < 0 or len(self.binary_str) < 2 * bit_length + 1):
            self.binary_str += pad(str(bin(self.bytes[0]))[2:])
            self.bytes = self.bytes[1:]
            bit_length = leading_zeros(self.binary_str)
        if len(self.bytes) == 0 and (bit_length < 0 or len(self.binary_str) < 2 * bit_length + 1):
            return None
        self.binary_str = self.binary_str[bit_length:]
        val = int(self.binary_str[:(bit_length + 1)], 2)
        self.binary_str = self.binary_str[(bit_length + 1):]
        return val

    def next_golumb(self, M, k):
        q = self.next_unary()
        if q is None:
            return None
        q -= 1
        while len(self.bytes) > 0 and len(self.binary_str) < k:
            self.binary_str += pad(str(bin(self.bytes[0]))[2:])
            self.bytes = self.bytes[1:]
        if len(self.binary_str) < k:
            return None
        r = int(self.binary_str[:k], 2)
        self.binary_str = self.binary_str[k:]
        return q * M + r

    def next_byte(self):
        val = int(self.bytes[0])
        self.bytes = self.bytes[1:]
        return val

def format(num):
    pattern = r"(?m)(?<=\d)\d{3}(?=(?:\d{3})*$)"
    return str(re.sub(pattern, r",\g<0>", str(num)))

def decode_file(filename):
    decoder = Decoder(filename)
    k = decoder.next_byte()
    M = 1 << k
    num_gaps = decoder.next_golumb(M, k)
    common_gaps = []
    for i in range(num_gaps):
        common_gaps.append(decoder.next_golumb(M, k))
    next = decoder.next_golumb(M, k)
    diffs = []
    while not next is None:
        diffs.append(2 * common_gaps[next])
        next = decoder.next_golumb(M, k)
    if "/1-" in filename or filename.endswith("/1"):
        diffs[0] = 1
    return diffs

def reset_database():
    for file in os.listdir(f"{BASE_DIR}/database"):
        os.remove(f"{BASE_DIR}/database/{file}")
    database = mariadb.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
    cursor = database.cursor()
    cursor.execute("DELETE FROM chunks")
    cursor.execute("INSERT INTO chunks (chunk_id, prime) VALUES (0, 2)")
    database.commit()
    database.close()

@app.route("/api/check", methods=['GET'])
def check_num():
    if not "num" in request.args:
        return "BAD", 400
    num = request.args["num"]
    if not num.isnumeric() or int(num) <= 0:
        return "BAD", 400
    num = int(request.args.get("num"))
    if num >= max_prime:
        return jsonify({'error': 'num too high'}), 400
    else:
        database = mariadb.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
        cursor = database.cursor()
        cursor.execute(f"SELECT * FROM chunks WHERE prime <= {num} ORDER BY chunk_id DESC LIMIT 1")
        chunk_id, last_prime = cursor.fetchone()
        num -= last_prime
        diffs = decode_file(f"{BASE_DIR}/database/{chunk_id + 1}")
        index = 0
        while num > 0:
            num -= diffs[index]
            index += 1
        if num == 0:
            packet = {'prime':True, 'index': chunk_id * CHUNK_SIZE + index + 1}
        else:
            packet = {'prime':False}
    return jsonify(packet)

def get_prime_at_index(index):
    database = mariadb.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
    cursor = database.cursor()
    chunk_id = index // CHUNK_SIZE
    dif = index - CHUNK_SIZE * chunk_id
    cursor.execute(f"SELECT * FROM chunks WHERE chunk_id = {chunk_id}")
    saved_prime = int(cursor.fetchone()[1])
    database.close()
    if dif > 0:
        diffs = decode_file(f"{BASE_DIR}/database/{chunk_id + 1}")
        for i in range(dif):
            saved_prime += diffs[i]
    return saved_prime

@app.route("/api/generate/by-index")
def generate_by_index():
    if not "lower" in request.args or not "upper" in request.args:
        return "BAD", 400
    lower = max(1, int(request.args["lower"]))
    upper = int(request.args["upper"])
    num_primes = upper - lower + 1
    current_chunk = lower // CHUNK_SIZE + 1
    database = mariadb.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
    cursor = database.cursor()
    cursor.execute(f"SELECT * FROM chunks WHERE chunk_id = {current_chunk - 1}")
    last_prime = cursor.fetchone()[1]
    database.close()
    diffs = decode_file(f"{BASE_DIR}/database/{current_chunk}")
    for i in range(lower % CHUNK_SIZE - 1):
        last_prime += diffs[i]
    primes = []
    num = lower
    for i in range(min(CHUNK_SIZE, num_primes)):
        if num // CHUNK_SIZE + 1 != current_chunk:
            current_chunk = num // CHUNK_SIZE + 1
            diffs = decode_file(f"{BASE_DIR}/database/{current_chunk}")
        primes.append(last_prime)
        last_prime += diffs[num % CHUNK_SIZE]
        num += 1
    packet = {"primes": primes}
    if num_primes > CHUNK_SIZE:
        packet["next"] = f"/api/generate/by-index?lower={lower + CHUNK_SIZE}&upper={upper}"
    return jsonify(packet)

@app.route("/api/generate/by-range")
def generate_by_range():
    if not "lower" in request.args or not "upper" in request.args:
        return "BAD", 400
    lower = max(2, int(request.args["lower"]))
    upper = int(request.args["upper"])
    database = mariadb.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
    cursor = database.cursor()
    cursor.execute(f"SELECT * FROM chunks WHERE prime <= {lower} ORDER BY chunk_id DESC LIMIT 1")
    current_chunk, prime = cursor.fetchone()
    current_chunk += 1
    diffs = decode_file(f"{BASE_DIR}/database/{current_chunk}")
    index = 0
    while prime < lower:
        prime += diffs[index]
        index += 1
    primes = []
    while prime <= upper and len(primes) < CHUNK_SIZE:
        primes.append(prime)
        if  index // CHUNK_SIZE + 1 != current_chunk:
            current_chunk = prime // CHUNK_SIZE + 1
            diffs = decode_file(f"{BASE_DIR}/database/{current_chunk}")
        prime += diffs[index % CHUNK_SIZE]
        index += 1
    packet = {"primes": primes}
    if len(primes) >= CHUNK_SIZE and prime <= upper:
        packet["next"] = f"/api/generate/by-range?lower={prime}&upper={upper}"
    return jsonify(packet)


@app.route("/api/index", methods=['GET'])
def get_prime():
    if not "n" in request.args or not request.args["n"].isnumeric():
        return "BAD", 400
    index = int(request.args.get("n"))
    if index > num_primes:
        return jsonify({"error": "n too high"}), 400
    elif index <= 0:
        return "BAD", 400

    if index == 0:
        packet = {"prime": "Zero"}
    elif index >= num_primes:
        packet = {"prime": "Unknown"}
    else:
        packet = {"prime": format(get_prime_at_index(index - 1)), "index": index}
    return jsonify(packet)

@app.route("/api/random", methods=['GET'])
def get_random():
    try:
        index = random.randint(0, num_primes - 1)
        packet = {"random": format(get_prime_at_index(index))}
    except Exception:
        packet = {"random": ""}
    return jsonify(packet)

@app.route("/", methods=["GET"])
def get_prime_html():
    return render_template("prime.html", num_primes=format(num_primes), max_num=format(max_prime), database_size=db_size, bits_per_prime=bits_per_prime, start_time=str(datetime.now()))

@app.route("/api", methods=["GET"])
def get_api_html():
    return render_template("api.html")


def emit_updates():
    global num_primes
    global max_prime
    global db_size
    global bits_per_prime
    database = mariadb.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
    cursor = database.cursor()
    while True:
        cursor.execute("SELECT * FROM chunks ORDER BY chunk_id DESC LIMIT 1")
        max_chunk_id, last_prime = cursor.fetchone()
        num_files = len(os.listdir(f"{BASE_DIR}/database"))
        if num_files > max_chunk_id:
            file_list = natsorted(os.listdir(f"{BASE_DIR}/database"))
            for i in range(max_chunk_id + 1, num_files):
                filename = file_list[i - 1]
                num, last_prime = filename.split('-')
                cursor.execute(f"INSERT INTO chunks (chunk_id, prime) VALUES ({i}, {last_prime})")
                os.rename(f"{BASE_DIR}/database/{filename}", f"{BASE_DIR}/database/{num}")
            database.commit()
            max_chunk_id = num_files - 1
        num_primes = CHUNK_SIZE * max_chunk_id
        max_prime = int(last_prime)
        db_size = subprocess.run(f"du -h {BASE_DIR}/database", shell=True, stdout=subprocess.PIPE).stdout.decode("utf-8").split('\t')[0]
        if max_chunk_id > 0:
            try:
                bits_per_prime = (1024 * 8 * int(subprocess.run(f"du {BASE_DIR}/database/{max_chunk_id}", shell=True, stdout=subprocess.PIPE).stdout.decode("utf-8").split('\t')[0])) / CHUNK_SIZE
                bits_per_prime = round(100 * bits_per_prime) / 100
            except Exception as e:
                pass
        socketio.emit("count_update", {'count': format(num_primes), 'max':format(max_prime), 'db_size':db_size, 'bpp': bits_per_prime})
        time.sleep(3)

def is_prime(n):
    for i in range(2, math.ceil(math.sqrt(n) + 1)):
        if n % i == 0:
            return False
    return True

def get_most_common(diffs):
    diff_set = set(diffs)
    frequencies = {}
    for d in diff_set:
        if not d in frequencies:
            frequencies[d] = 0
        frequencies[d] += diffs.count(d)
    item_list = sorted(frequencies.items(), key=lambda u: u[1], reverse=True)
    return [i[0] for i in item_list]

def unary_length(n):
    return 2 * (n + 1).bit_length() - 1

def golumb_length(n, M=4):
    q = n // M
    k = M.bit_length()
    return unary_length(q) + k

if __name__ == '__main__':
    if RESET_DATABASE:
        reset_database()
        process = subprocess.Popen(['./calculate-primes'])
    else:
        database = mariadb.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
        cursor = database.cursor()
        cursor.execute("SELECT * FROM chunks ORDER BY chunk_id DESC LIMIT 1")
        chunk_id, start = cursor.fetchone()
        print(f"Starting with {start} and chunk {chunk_id}")
        process = subprocess.Popen(['./calculate-primes', str(start), str(chunk_id + 1)])
    threading.Thread(daemon=True).start()
    thread1 = threading.Thread(target=emit_updates)
    thread1.start()
    app.run(host='0.0.0.0', port=5000,debug=False)
