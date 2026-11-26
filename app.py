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

def format(num):
    pattern = r"(?m)(?<=\d)\d{3}(?=(?:\d{3})*$)"
    return str(re.sub(pattern, r",\g<0>", str(num)))

def leading_zeros(str):
    for i, char in enumerate(str):
        if char != '0':
            return i
    return -1

def pad(str):
    return ("0" * (8 - len(str))) + str

def decode_file(filename):
    with open(filename, 'rb') as f:
        bytes = f.read()
    k = int(bytes[0])
    bytes = bytes[1:]
    M = 1 << k
    output = []
    val = ""
    for i, byte in enumerate(bytes):
        val += pad(str(bin(byte))[2:])
        bit_length = leading_zeros(val)
        enc_length = (2 * bit_length + k) if bit_length > 0 else (k + 1)
        while bit_length >= 0 and len(val) >= enc_length:
            if bit_length > 0:
                val = val[bit_length:]
                num = int(val[:bit_length], 2) * M
                val = val[bit_length:]
            else:
                num = 0
                val = val[1:]
            num += int(val[:k], 2)
            val = val[k:]
            output.append(2 * num)
            bit_length = leading_zeros(val)
            enc_length = (2 * bit_length + k) if bit_length > 0 else (k + 1)
    if filename.endswith('/1'):
        output[0] = 1
    return output


def reset_database():
    for file in os.listdir(f"{BASE_DIR}/database"):
        os.remove(f"{BASE_DIR}/database/{file}")
    database = mariadb.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
    cursor = database.cursor()
    cursor.execute("DELETE FROM chunks")
    cursor.execute("INSERT INTO chunks (chunk_id, prime) VALUES (0, 2)")
    database.commit()
    database.close()

@app.route("/api/num_check", methods=['GET'])
def check_num():
    try:
        num = int(request.args.get("num"))
        num_cpy = num
        if num >= max_prime:
            packet = {'error': 'num too high'}
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
                packet = {'prime':True, 'index':format(CHUNK_SIZE * chunk_id + index + 1), 'input':format(num_cpy)}
            else:
                packet = {'prime':False, 'input':format(num_cpy)}
    except Exception as e:
        print(e)
        packet = {'error':str(e)}
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


@app.route("/api/index", methods=['GET'])
def get_prime():
    try:
        index = int(request.args.get("num"))
        if index == 0:
            packet = {"prime": "Zero"}
        elif index >= num_primes:
            packet = {"prime": "Unknown"}
        else:
            packet = {"prime": format(get_prime_at_index(index - 1)), "index": format(index)}
    except Exception as e:
        print(e)
        packet = {"prime": "Unknown"}
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
