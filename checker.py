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

USERNAME = "cifadmin"
PASSWORD = "A4;hXuP/n0mlzFu;2]6&@GL;+"

def is_prime(n):
    if n % 2 == 0:
        return False
    for i in range(3, math.ceil(1 + math.sqrt(n)), 2):
        if n % i == 0:
            return False
    return True

database = mysql.connector.connect(host="localhost", user=USERNAME, password=PASSWORD, database="PRIMES")
cursor = database.cursor()
cursor.execute("SELECT * FROM primes WHERE number >= 2 ORDER BY number ASC LIMIT 1000000")
print(len(cursor.fetchmany(1000000)))
database.close()
