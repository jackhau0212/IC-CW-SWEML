#!/usr/bin/env python3

import argparse
import sys
import signal
import socket
import csv
import pickle
from datetime import datetime
import simulator
from datetime import datetime
import time
from time import perf_counter
import numpy as np
import traceback
import os
from prometheus_client import Counter, Histogram, Gauge
from prometheus_client import start_http_server


start_http_server(8000)

## Consts for communicating with the hospital server ## 
ACK = [ 
    "MSH|^~\&|||||20240129093837||ACK|||2.5",
    "MSA|AA",
]
MLLP_START_OF_BLOCK = 0x0b
MLLP_END_OF_BLOCK = 0x1c
MLLP_CARRIAGE_RETURN = 0x0d


Total_messages_counter = Counter('Total_messages_counter', 'Total number of messages processed')
Total_numbeer_blood_counter = Counter('Total_numbeer_blood_counter', 'Total number of blood tests processed')
Number_positive_counter = Counter('Number_positive_counter', 'Total number of positive predictions')
Number_of_non_200_counter = Counter('Number_of_non_200_counter', 'Total number of non-200 responses')
Number_of_recconections_counter = Counter('Number_of_recconections_counter', 'Total number of reconnections')
Distribuition_bloods= Histogram("Distribuition_bloods", 'distribuitions of bloods',buckets=[80, 90, 105, 120,140, 'inf'])
Latency_times= Gauge("Latency_times", '99 percentile distribuitions of bloods')


def sigterm_handler(signum: int, frame: None, database: dict) -> None:
    """
    Handles receiving a SIGTERM signal. Saves the 
    database in its current state and exists the program
    """
    with open("/state/database.pkl", "wb") as pkl:
        pickle.dump(database, pkl)
    sys.exit(0)

def select_buckets(data):
    """
    Converts data to buckets for Prometheus client.
    """
    # Calculate quantiles to determine bucket boundaries
    quantiles = np.linspace(0, 1, 6)
    boundaries = np.quantile(data, quantiles)

    # Convert boundaries to Prometheus bucket format
    buckets = [float('-inf')] + list(boundaries[1:-1]) + [float('inf')]
    return buckets

def from_mllp(buffer: bytes) -> list: 
    """
    Removes MLLP framing from message received from buffer to reveal
    HL7 message. 

    Args:
        buffer {bytes} - data from buffer, expected to contain a single HL7 message

    Returns:
        {list} - HL7 message
    """
    return str(buffer[1:-3], "ascii").split("\r") # Strip MLLP framing and final \r

def to_mllp(segments:list) -> bytes:
    """
    Adds MLLP framing around to HL7 message and converts to bytes

    Args:
        segments {list} - message to add framing to and convert to bytes

    Returns:
        {bytes} - MLLP framed message
    """
    m = bytes(chr(simulator.MLLP_START_OF_BLOCK), "ascii")
    m += bytes("\r".join(segments) + "\r", "ascii")
    m += bytes(chr(simulator.MLLP_END_OF_BLOCK) + chr(simulator.MLLP_CARRIAGE_RETURN), "ascii")
    return m


def _parse_history_file(database: dict, file_path: str) -> dict:
    """
    Parses a .txt file of PAS messages to update the current 
    state of who is in the hospital. Used as a backup to restore
    system awareness of who is in the hospital.

    Args:
        database {dict}: current database
        file_path {str}: path of backup.txt

    Returns:
        {dict}: updated database 
    
    """
    with open(file_path, 'r') as file:
        # skip first two rows (headers)
        next(file)
        next(file)
        while True:
            try:
                line1 = next(file).strip()  # Read the first line
                line2 = next(file).strip()  # Read the next line
                mrn = line2.split("|")[3]
                msg = [line1, line2]
                pas_process(mrn, msg, database)
            except StopIteration:  # End of file
                break
    return database

def convert_history_to_dictionary(history_filename: str) -> dict:
    """
    Reads historical patient data stored in a persistant format
    (e.g. pkl, csv or txt) and loads it into memory via a dict.

    Has 2 modes of operation:
        1. if a pkl file exists (e.g. from a previous runtime) then
            load from there
        2. otherwise (e.g. from a 'fresh' start) load from historical csv 
            file + backup.txt which contains all current hospital admissions 
    
    backup.txt is assumed and is included in our Dockerfile as a result
    of an incident which required a restart. 

    Args:
        history_filename {str} - path to csv file of patient data
    
    Returns:
        {dict} - dictionary of patient data
    """
    if os.path.exists("/state/database.pkl"): # if pickle file exists then load from pickle
        with open("/state/database.pkl", "rb") as pkl:  
            database = pickle.load(pkl)

    else: # otherwise load from original csv 
        database = {}
        with open(history_filename, "r") as f:
            reader = csv.reader(f)
            next(reader) # skip header
            for row in reader:
                database[row[0]] = {
                    "results": [float(x) for x in row[2:len(row):2] if x != ""]
                }
        database = _parse_history_file(database, "backup.txt")
        with open("/state/database.pkl", "wb") as pkl:  # write to pickle for future use
            pickle.dump(database, pkl)
       
    return database

def send_message(mrn: str, pager_host: str, pager_port: int) -> None:
    """
    Sends message to pager containing mrn via HTTP request.

    Args:
        mrn {str} - medical record number to send
        pager_host {str} - host name for pager
        pager_port {int} - port for pager
    Returns:
        None
    """
    # Construct the HTTP request
    request = f"POST /page HTTP/1.0\r\n"
    request += f"Content-type: text/plain\r\n"
    request += f"Content-Length: {len(mrn)}\r\n"
    request += "\r\n"
    request += f"{mrn}"

    attempts = 0
    max_attempts = 100

    # Create a new socket for the pager server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s_pager:

        while attempts < max_attempts:
            try:
                s_pager.connect((pager_host, pager_port))  # Attempt to to the pager server
                s_pager.sendall(request.encode())  # Send the HTTP request
                response = s_pager.recv(1024)  # Receive response
                break  
            except (socket.error, socket.timeout): # retry 
                print(f"Error sending to pager! Attempt {attempts}/{max_attempts} ")
                attempts+=1
                time.sleep(5)
                
        print("Paged successfully!")
        if response.decode().split(" ")[1] !='200':
            Number_of_non_200_counter.inc()


def pas_process(mrn: str, message: list, database: dict) -> None:
    """
    Processes HL7 messages from PAS, updating the current database.

    Args:
        mrn {str}: admitted patient mrn 
        message {list}: HL7 message from PAS
        database {dict}: database  
    Returns:
        None
    """
    if "A03" in message[0].split("|")[8]: # discharge patient 
        return
    else:
        current_date = datetime.strptime(message[0].split("|")[6], '%Y%m%d%H%M%S')
        # use patient info to update database
        dob = datetime.strptime(message[1].split("|")[7], '%Y%m%d')
        age = current_date.year - dob.year - ((current_date.month, current_date.day) < (dob.month, dob.day))
        sex = message[1].split("|")[8]

        if mrn in database:
            # set/update the sex and age parameters 
            database[mrn]["sex"] = sex
            database[mrn]["age"] = age

        else: # add new patient's information
            database[mrn] = {
                "results": [],
                "sex": sex,
                "age": age
            }
    
def lims_process(patient_id: str, message: list, database: dict,Bloods:list) -> np.array:
    """
    Processes HL7 messages from LIMS, producing a np.array with age, gender and
    5 most recent test that can be used to inference with the model.

    Args:
        mrn {str}: admitted patient mrn 
        message {list}: HL7 message from LIMS
        database {dict}: database  
    Returns:
        {np.array}: array of 

    """
    newest_test_result = float(message[3].split("|")[5]) # get test result
    Bloods+=[newest_test_result]
    Distribuition_bloods.observe(newest_test_result)
    database[patient_id]["results"].append(newest_test_result) # add to database

    n = len(database[patient_id]["results"])

    # Create test point consiting of age, gender and 5 most recent test results
    if n >= 5:
        test_point = database[patient_id]["results"][-5:]
    else:
        mean = np.mean(database[patient_id]["results"])
        test_point = [mean for i in range(5-n)]+database[patient_id]["results"]

    if database[patient_id]["sex"] == 'M':
        test_point.insert(0,1)
    else:
        test_point.insert(0,0)
    test_point.insert(0,database[patient_id]["age"])
    test_point = np.array(test_point).reshape(1,-1)
    # print(patient_id, test_point)
    return test_point

def _evaluation(responses: dict, expected_aki_file: str) -> None:
    """
    Runs evaluation on the inference performance including response
    time for detecting akis and the number of akis detected. 

    Args:
        responses {dict} - patient mrn and response time for alterted aki events
        expected_aki_file {str} - csv file with patient mrn who are expected to have an aki event
    Returns:
        None - prints latency and accuracy metrics
    
    """
    times = [t for t in responses.values()] # response times when aki is detected
    expected_akis = set() # patient id we expect an aki response from
    reported_akis = {mrn for mrn in responses.keys()} # patient ids we alerted an aki response 

    # report latency metrics 
    print(f"Mean: {np.mean(times)}")
    print(f"90th percentile: {np.percentile(times, 90)}")
    print(f"Number of aki events: {len(times)}")

    # report accuracy metrics 
    with open(expected_aki_file) as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            expected_akis.add(row[0])
    print(f"Missing aki events: {len(expected_akis-reported_akis)}")
    print(f"Incorrect aki events: {len(reported_akis-expected_akis)}")


signal.signal(signal.SIGTERM, sigterm_handler) # init sigterm handler

def main(args):
    """
    Runs live inference with the AKI detection system

    """
    # prometheus logging
    Times=[]
    Bloods=[]

    # attempts for time out condition
    attempts = 0
    max_attempts = 100

    responses = {}  # track aki events with patient numbers and response times for evaluation
    with open('trained_model.pkl', 'rb') as file:  # load model
        trained_model = pickle.load(file)

    database = convert_history_to_dictionary("/hospital-history/history.csv")  # load historical data 
    while attempts < max_attempts:

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:  # create IPv4 TCP socket with MLLP
            
            try:
                s.connect((args.mllp_address.split(":")[0], int(args.mllp_address.split(":")[1])))  # establish connection
                print("Connection established!")

            except (socket.error, socket.timeout) as e: # catch errors establishing connection
                print(f"Failure establishing connection! Attempt {attempts}/{max_attempts} to reconnect...")
                time.sleep(3)
                attempts += 1
                continue

            try: # with connection established 

                while True: # run inference loop
                    buffer = s.recv(1024)  # read stream 
                    st = perf_counter()  # start timer

                    if len(buffer) == 0:  # breaks if connection is closed
                        break
                    
                    try: 
                        
                        message = from_mllp(buffer)  # remove MLLP framing
                        Total_messages_counter.inc()
                        is_PAS = True if ("ADT" in message[0].split("|")[8]) else False  # determine message type
                        mrn = message[1].split("|")[3]

                        if is_PAS: 
                            pas_process(mrn, message, database) # process PAS message
                        else:  
                            Total_numbeer_blood_counter.inc()
                            test_point = lims_process(mrn, message, database, Bloods) # process LIMS message
                            
                            prediction_num = trained_model.predict(test_point)[0] # inference
                            if prediction_num == 1: #if AKI detected
                                Number_positive_counter.inc()
                                send_message(mrn, args.pager_address.split(":")[0], int(args.pager_address.split(":")[1])) # send message to pager via HTTP
                                response_time = perf_counter() - st # calculate response time
                                Times+=[response_time]
                                responses[mrn] = response_time
                                response_time=Latency_times.set(np.percentile(Times, 99))

                    except:
                        pass

                    pickle.dump(database, open("/state/database.pkl", 'wb'))
                    s.sendall(to_mllp(ACK))
        
            except (socket.timeout, socket.error): # catch errors breaking connection
                print(f"Connection broke!")
                time.sleep(2)
        
    if args.evaluate: # evaluation mode
        _evaluation(responses, "aki.csv")

if __name__ == "__main__":
    
    MLLP_ADDRESS = os.environ["MLLP_ADDRESS"]
    PAGER_ADDRESS = os.environ["PAGER_ADDRESS"]
    parser = argparse.ArgumentParser()
    parser.add_argument("--mllp_port", type=int, default=8440)
    parser.add_argument("--pager_port", type=int, default=8441)
    parser.add_argument("--mllp_address", type=str, default=MLLP_ADDRESS)
    parser.add_argument("--pager_address", type=str, default=PAGER_ADDRESS)
    parser.add_argument("--evaluate", type=bool, default=False)
    parser.add_argument("--model", type=str, default="trained_model.pkl")
    args = parser.parse_args()
    main(args)