#!/usr/bin/env python3
import schedule
import subprocess
import json
import requests
from influxdb import InfluxDBClient
import logging
import os
import time
import dateutil.parser
import sys
import argparse

# Runs Ookla speedtest CLI client, posts resulting data to influxdb
# See: https://www.speedtest.net/apps/cli


# Influx configuration
INFLUX_HOST = os.getenv("INFLUX_HOSTNAME", "localhost")
INFLUX_DATABASE = os.getenv("INFLUX_DATABASE", "speedtest")

# Example speedtest CLI json output: speedtest -f json
# {
#  "type": "result",
#  "timestamp": "2023-05-28T15:47:52Z",
#  "ping": {
#    "jitter": 0.709,
#    "latency": 10.829,
#    "low": 9.967,
#    "high": 11.327
#  },
#  "download": {
#    "bandwidth": 50609814,
#    "bytes": 425087912,
#    "elapsed": 8415,
#    "latency": {
#      "iqm": 10.635,
#      "low": 9.907,
#      "high": 11.937,
#      "jitter": 0.476
#    }
#  },
#  "upload": {
#    "bandwidth": 64929665,
#    "bytes": 363032856,
#    "elapsed": 5604,
#    "latency": {
#      "iqm": 10.966,
#      "low": 10.151,
#      "high": 235.815,
#      "jitter": 4.404
#    }
#  },
#  "packetLoss": 0,
#  "isp": "Cincinnati Bell",
#  "interface": {
#    "internalIp": "192.168.0.1",
#    "name": "enp34s0",
#    "macAddr": "00:D8:61:59:83:33",
#    "isVpn": false,
#    "externalIp": "163.182.6.32"
#  },
#  "server": {
#    "id": 48322,
#    "host": "speedtest-cvg.wsgo.net",
#    "port": 8080,
#    "name": "Waddell Solutions Group",
#    "location": "Cincinnati, OH",
#    "country": "United States",
#    "ip": "198.98.15.250"
#  },
#  "result": {
#    "id": "10908009-440e-40f3-83b8-b75f19ed676a",
#    "url": "https://www.speedtest.net/result/c/10908009-440e-40f3-83b8-b75f19ed676a",
#    "persisted": true
#  }
#}

def speedtest_results():
    # Execute the command and capture the output
    logging.debug("Running speed test")
    result = subprocess.run("/usr/bin/speedtest -f json", shell=True, capture_output=True, text=True)
    #result = subprocess.run("cat /tmp/speedtest.json", shell=True, capture_output=True, text=True)

    # Check if the command was successful
    if result.returncode == 0:
        # Parse the JSON output
        try:
            json_output = json.loads(result.stdout)
            return json_output
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON: {e}")
            return None
    else:
        print(f"Command failed with exit code {result.returncode}")
        return None


# Flattest nested structures in a dict to produce a 1-level-deep dict, using a separator ('.') to indicate nesting
def flatten_dict(dictionary, parent_key='', sep='.'):
    flattened_dict = {}
    if not dictionary:
        logging.error("Empty dictionary, cannot flatten")
        return {}
    for key, value in dictionary.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        if isinstance(value, dict):
            flattened_dict.update(flatten_dict(value, new_key, sep=sep))
        else:
            flattened_dict[new_key] = value
    return flattened_dict


def convert_results_to_influx_datapoint(results_json):
    # Flatten the Ookla data structure into just one level
    flattened = flatten_dict(results_json)
    point = {"measurement": "speedtest"}
    tags = {}

    # Fix the datatypes of some fields
    if isinstance(flattened.get("packetLoss", None), int):
        flattened['packetLoss'] = float(flattened['packetLoss'])

    # Pull out some values as tags
    tag_fields = ["isp","server.ip","server.name","server.id"]
    for f in tag_fields:
        tag_value = flattened.get(f, None)
        if(tag_value):
            tags[f] = tag_value
    point['tags'] = tags
    
    # Use the full list as fields
    point['fields'] = flattened

    return point


def create_point(device, measurement_name, value, time=None):
    point = {
        "measurement": measurement_name,
        "tags": {
            "deviceId": device.device_id,
            "deviceName": device.device_name
        },
        "fields": {
            "value": value
        }
    }
    if time:
        converted_time = dateutil.parser.isoparse(time).strftime('%Y-%m-%dT%H:%M:%SZ')
        point["time"]=converted_time

    return point

# Writing to Influx using the Python API (https://influxdb-python.readthedocs.io/en/latest/api-documentation.html#influxdb.InfluxDBClient.write_points):
def post_to_influx(data_points):
    logging.debug(f"Posting {len(data_points)} data points to {INFLUX_HOST}:{INFLUX_DATABASE}")
    client = InfluxDBClient(INFLUX_HOST, 8086, database=INFLUX_DATABASE)
    result = client.write_points(data_points, time_precision='s')
    if not result:
        logging.error(f"Write to influxdb failed. Points: {data_points}")
    logging.debug(f"Post complete")


def test_and_record():
    result_json = speedtest_results()
    logging.debug(f"results: {result_json}")
    datapoint = convert_results_to_influx_datapoint(result_json)
    logging.debug(f"datapoint: {datapoint}")

    post_to_influx([datapoint])


logging.basicConfig(level=logging.INFO, stream = sys.stdout, format='%(levelname)s: %(message)s')
# Parse arguments
parser = argparse.ArgumentParser(description='Runs Ookla speedtest CLI client, posts resulting data to influxdb')
parser.add_argument('--daemon', action='store_true', dest='daemon', help='Run as a daemon, testing speed every hour (by default)')
parser.add_argument('--interval-mins', action='store', dest='interval_mins', type=int, default=60, help='Interval (in minutes) between checks in daemon mode')
parser.add_argument('--debug', action='store_true', dest='debug', help='Enable debug logging')
args = parser.parse_args()

if args.debug:
    logging.root.setLevel(logging.DEBUG)


if args.daemon:
    schedule.every(args.interval_mins).minutes.do(test_and_record)
    test_and_record()
    while True:
        schedule.run_pending()
        time.sleep(60)
else:
    test_and_record()
