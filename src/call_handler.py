#!/usr/bin/python3

import os
import openai
from typing import List
from flask import Response, Request
from twilio.twiml.voice_response import VoiceResponse
from twilio.rest import Client

class CallHanlder:
    def __init__(self) -> None:
        # Keeps track of the callers conversation
        self.callerConversations = dict()
        openai.api_key = os.environ.get('OPENAI_API_KEY')
        self.twilioClient = Client(
            os.environ.get('TWILLO_ACCOUNT_SID'),
            os.environ.get('TWILLO_AUTH_TOKEN')
        )

    def _createChatCompletion(self, messages) -> dict:
        '''
        Create a chat completion using OpenAI API
        Args:
            messages: list of dictionaries (keys: role and content)
        Returns:
            dict: ai response to user voice input
        '''
        completion = openai.ChatCompletion.create(
            model='gpt-3.5-turbo',
            messages=messages,
            temperature=0.5
        )
        return {
            'role': completion.choices[0].message.role,
            'content': completion.choices[0].message.content.replace('/^\w+:\s*/i', '').strip()
        }

    def _formatAiResponse(self, aiResponse: str) -> VoiceResponse:
        '''
        Adds pauses to ai response for a better caller experience.
        Args:
            aiResponse: string
        Returns:
            VoiceResponse: TwiML generate call
        '''
        twiml = VoiceResponse()
        if '\n' in aiResponse:
            for part in aiResponse.split('\n'):
                if not part:
                    twiml.pause(length=1)
                else:
                    twiml.say(voice='Polly.Joanna-Neural', message=part)
            self.logger.info(str(twiml))
        else:
            twiml.say(voice='Polly.Joanna-Neural', message=aiResponse)
        return twiml

    def _shouldSendText(self, conversation: List[dict]):
        '''
        Determines if a text should be sent after scheduling appointment
        Args:
            list: an array of dictionaries contain conversation thread
        Returns:
            bool: if true, send sms
            str: message text to send
            str: number to sms
        '''
        aiResponse = self._createChatCompletion(
            conversation + [{ 'role': 'assistant', 'content': 'with a yes or no response, should a text be sent now?' }]
        )
        conversation.append(aiResponse)
        shouldSend = False
        messageBody = None
        toNumber = None
        if 'Yes' in aiResponse:
            shouldSend = True
            messageBody = self._createChatCompletion(
                conversation + [{ 'role': 'system', 'content': 'print text message to send' }]
            )['content']
        return shouldSend, messageBody, toNumber

    def startCall(self, request: Request) -> Response:
        '''
        Args:
            request: Flask Request
        Returns:
            Response: response containing TwiML generate call
        '''
        
        call_sid = request.values['CallSid']
        # New call started, adding Twilio sid to the messages dict
        if not self.callerConversations.get(call_sid):
            self.callerConversations[call_sid] = [
                {
                    'role': 'system',
                    'content': "You're name is Joanna. You are a thoughful and helpful assistant for a doctor's office. Your goal is to help someone schedule a doctors appointment. You need to collection the following information: first name, last name, date of birth, insurance provider, insurance id, name of person responsible for paying, ask if they were referred (either by a person or another provider), address (must have house number, street name, city, state and zip code), marital status, contact number, and email (ensure email provide is a valid email format). "
                        "The data the caller provides should be stored as a JSON object, to be accessed later. If caller indicates they are the party responsible for paying, save their name for that information. " +
                        "Before you can proceed with asking about reason for calling, please read back the information to the caller and confirm if the information is correct, if it is not ask caller to correct any information. " +
                        "If all the information is correct, ask about medical complaint. " +
                        "Create a doctor's office, office needs the following information: address and office number. " +
                        "Create doctor recommendations that can help with medical complaint. " +
                        "All doctors are from the same office. After they have seleced a doctor, list available times and dates, use fake data. " +
                        "After caller selects the desired appointment, please send a text to the caller with all the information regarding the appointment. "
                },
                {
                    'role': 'assistant',
                    'content': 'Hello, my name is Joanna! I am looking forward to helping you today. Before I can do that, ' +
                        'I just need to collect some information from you. Could you please provide me with your first and last name?'
                }
            ]

        twiml = VoiceResponse()
        twiml.say(
            voice='Polly.Joanna-Neural', 
            message='Hello, my name is Joanna! I am looking forward to helping you today. Before I can do that, I just need to collect some information from you. Could you please provide me with you first and last name?'
        )
        twiml.gather(
            input='speech',
            action='/respond',
            speechModel='experimental_conversations', 
            speechTimeout='auto'
        )
        return Response(str(twiml), content_type='application/xml', status=200)

    def transcribe(self) -> Response:
        '''
        Captures caller's speech
        Returns:
            Response: response containing TwiML generate call
        '''
        
        twiml = VoiceResponse()
        twiml.gather(
            input='speech', 
            action='/respond',
            speechModel='experimental_conversations', 
            speechTimeout='auto'
        )
        twiml.redirect('/end-call', method='GET')
        return Response(str(twiml), content_type='application/xml', status=200)

    def response(self, request: Request) -> Response:
        '''
        Generates AI response from caller's input
        Args:
            request: Flask Request
        Returns:
            Response: response containing TwiML generate call
        '''

        call_sid = request.values.get('CallSid')
        voiceInput = request.values.get("SpeechResult")

        # Adding ther caller's response the the message list
        self.callerConversations[call_sid].append(
            { 'role': 'user', 'content': voiceInput }
        )

        aiResponse = self._createChatCompletion(
            self.callerConversations[call_sid]
        )
        self.callerConversations[call_sid].append(aiResponse)
        
        if 'send you a text message' in aiResponse.get('content'):
            shouldSendText, textBody, toNumber = self._shouldSendText(
                self.callerConversations[call_sid]
            )

            if shouldSendText and textBody:
                twiml = VoiceResponse()
                twiml.redirect('/send_sms')
                response = Response(str(twiml), content_type='application/xml', status=200)
                response.set_cookie('textBody', textBody, path='/')
                response.set_cookie('toNumber', toNumber, path='/')
                return response

        # Generate some <Say> TwiML using the AI response
        twiml = self._formatAiResponse(aiResponse.get('content'))

        # Redirect to the `/transcribe` endpoint to capture the caller's speech
        twiml.redirect('/transcribe', method='POST')

        # Return the response to the handler
        return Response(str(twiml), content_type='application/xml', status=200)

    def endCall(self, request: Request) -> Response:
        '''
        Ends call after sending text message or no input is recieved from caller
        Args:
            request: Flask Request
        Returns:
            Response: response containing TwiML generate call
        '''

        twiml = VoiceResponse()
        twiml.say('Thank you, goodbye!')
        twiml.hangup()
        del self.callerConversations[request.values['CallSid']]
        return Response(str(twiml), content_type='application/xml', status=200)

    def sendSMS(self, request: Request) -> Response:
        '''
        Sends a text message confirming doctor's appointment
        Args:
            request: Flask Request
        Returns:
            Response: response containing TwiML sending sms
        '''

        cookies = dict(request.cookies)
        toNumber = cookies.get("toNumber")
        textBody = cookies.get("textBody")
        sms_message = self.twilioClient.messages.create(
            to='+1'+toNumber,
            from_=os.environ.get('CALL_CENTER_NUMBER'),
            body=textBody
        )
        if not sms_message.error_code:
            return self.endCall()
        else:
            response = Response()
            response.status = 'Internal Service Error'
            response.status_code = 500
            return response
