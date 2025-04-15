#!/usr/bin/env python
import asyncio
import websockets
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_ID = "gpt-4o-realtime-preview"
VOICE = "alloy"
INSTRUCTIONS = "تحدث بالعربية فقط. كن مساعدًا ودودًا وتجاوب بشكل طبيعي مع المتصل."

async def send_session_update(openai_ws):
    """Send session update to OpenAI WebSocket."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": INSTRUCTIONS,
            "modalities": ["text", "audio"]
        }
    }
    await openai_ws.send(json.dumps(session_update))

async def handle_call(twilio_ws, path):
    """Handle an incoming call from Twilio."""
    print(f"New connection from {twilio_ws.remote_address}")
    stream_sid = None
    
    uri = f"wss://api.openai.com/v1/realtime?model={MODEL_ID}"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }
    
    try:
        async with websockets.connect(uri, extra_headers=headers) as openai_ws:
            print("Connected to OpenAI")
            await send_session_update(openai_ws)
            
            async def forward_twilio_to_openai():
                nonlocal stream_sid
                try:
                    async for message in twilio_ws:
                        data = json.loads(message)
                        event = data.get("event")
                        
                        if event == "start":
                            print("Call started")
                            stream_sid = data.get("streamSid")
                            
                        elif event == "media":
                            # Forward audio to OpenAI
                            media_payload = {
                                "type": "audio",
                                "data": data["media"]["payload"]
                            }
                            await openai_ws.send(json.dumps(media_payload))
                            
                        elif event == "stop":
                            print("Call ended")
                            # Send end message to OpenAI
                            await openai_ws.send(json.dumps({"type": "end"}))
                            break
                            
                        elif event == "mark":
                            # Handle mark events if needed
                            pass
                            
                except websockets.exceptions.ConnectionClosed as e:
                    print(f"Twilio WebSocket closed: {e}")
                except Exception as e:
                    print(f"Error in Twilio handler: {e}")
            
            async def forward_openai_to_twilio():
                try:
                    async for message in openai_ws:
                        # Parse the message from OpenAI
                        data = json.loads(message)
                        message_type = data.get("type")
                        
                        if message_type == "audio":
                            # Format audio for Twilio
                            twilio_message = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {
                                    "payload": data["data"]
                                }
                            }
                            await twilio_ws.send(json.dumps(twilio_message))
                            
                        elif message_type == "message":
                            # Handle text messages if needed
                            print(f"OpenAI message: {data.get('content')}")
                            
                        elif message_type == "error":
                            # Handle OpenAI errors
                            print(f"OpenAI error: {data.get('message')}")
                            
                except websockets.exceptions.ConnectionClosed as e:
                    print(f"OpenAI WebSocket closed: {e}")
                except Exception as e:
                    print(f"Error in OpenAI handler: {e}")
            
            # Run both forwarding tasks concurrently
            await asyncio.gather(
                forward_twilio_to_openai(),
                forward_openai_to_twilio()
            )
    except Exception as e:
        print(f"Connection error: {e}")

async def main():
    port = int(os.getenv("PORT", 8081))
    print(f"✅ Arabic voice assistant is running on port {port}")
    
    async with websockets.serve(handle_call, "0.0.0.0", port): 
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
