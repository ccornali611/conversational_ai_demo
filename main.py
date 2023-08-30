#!/usr/bin/python3

import os
import logging
import http
from flask import (Flask, request,  Response)
from src import call_handler

logging.basicConfig(filename='record.log', level=logging.INFO)

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
callHandler = call_handler.CallHanlder

@app.route('/health-check', methods=['GET'])
def health_check():
    return Response(status=http.HTTPStatus.OK)

@app.route('/start-call', methods=['POST', 'GET'])
def start_call():
    return callHandler.startCall(request)

@app.route('/respond', methods=['POST', 'GET'])
def respond():
    return callHandler.response(request)

@app.route('/transcribe', methods=['POST', 'GET'])
def transcribe():
    return callHandler.transcribe()

@app.route('/end-call', methods=['POST', 'GET'])
def end_call():
    return callHandler.endCall(request)

@app.route('/send-sms', methods=['POST', 'GET'])
def send_sms():
    return callHandler.sendSMS(request)

if __name__ == '__main__':
    app.run(host=os.environ.get('HOST'), port=os.environ.get('PORT'))
