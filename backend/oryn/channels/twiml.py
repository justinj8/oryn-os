"""TwiML responses, built with Twilio's own library (handles XML escaping)."""

from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import Gather, VoiceResponse

VOICE = "Polly.Joanna"


def message(text: str) -> str:
    r = MessagingResponse()
    r.message(text)
    return str(r)


def gather(prompt: str, action_url: str) -> str:
    r = VoiceResponse()
    g = Gather(input="speech", action=action_url, method="POST", speech_timeout="auto")
    g.say(prompt, voice=VOICE)
    r.append(g)
    r.say("Sorry, I didn't catch that. Goodbye.", voice=VOICE)
    return str(r)


def say_and_gather(text: str, action_url: str) -> str:
    return gather(text, action_url)


def hangup(text: str) -> str:
    r = VoiceResponse()
    r.say(text, voice=VOICE)
    r.hangup()
    return str(r)
