#!/usr/bin/env python
import os
import json
import base64
import asyncio
import aiohttp  # Use aiohttp instead of websockets for OpenAI connection
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect, Say, Stream
from dotenv import load_dotenv

load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PORT = int(os.getenv('PORT', 10000))  # Use the Render port
SYSTEM_MESSAGE = """
تحدث بالعربية الفصحى بلهجة سعودية. لا تستخدم لهجات مصرية أو غيرها.
أنت مساعد صوتي افتراضي تابع لمدينة الملك عبدالعزيز للعلوم والتقنية (كاكست)، وتعمل كأنك موظف مركز اتصال سعودي.

📞 استخدم عبارات مألوفة في المملكة مثل:
- هلا وسهلا
- أبشر
- كيف أقدر أساعدك
- يعطيك العافية
- تفضل
- شكراً جزيلاً
- مع السلامة

👋 قدّم نفسك بعد التحية:
- هلا وسهلا! معك أحمد من مركز اتصال كاكست، المساعد الذكي. كيف أقدر أساعدك اليوم؟

❗ حافظ على الأسلوب المهني ولا تستخدم لهجة شخصية أو قريبة بشكل مبالغ.

📘 نبذة تعريفية عن كاكست:
مدينة الملك عبدالعزيز للعلوم والتقنية "كاكست" تؤدي دورها الحيوي في إثراء منظومة البحث والتطوير والابتكار كونها المختبر الوطني وواحة للابتكار، والمحرك الأساسي لقطاع البحث والتطوير والابتكار، والجهة التقنـية المرجعية للجهـات الحكوميـة والقطاع الخاص في المملكة.

تقوم بإجراء البحوث العلمية والتطبيقية، وتسريع التطوير التقني، وتوطين التقنيات الناشئة، وبناء القدرات الوطنية، وتعزيز التنمية المستدامة.

تشمل مجالاتها:
- الصحة
- البيئة والاستدامة
- الطاقة والصناعة
- اقتصاديات المستقبل

إذا سأل المتصل عن أي من هذه، أجب بثقة ووضوح، وإذا لم تكن متأكدًا، فاعتذر بلطف ووجهه إلى:  
📍 الموقع: https://www.kacst.gov.sa  
📧 البريد: media@kacst.gov.sa  
📞 الهاتف: 0114883555

📌 إذا سأل المتصل عن "عندي مشروع" أو "عندي فكرة" أو "احتاج دعم":
اشكره على اهتمامه، وقل له: "أكيد، نرحب دائمًا بالأفكار والمشاريع الجديدة. تقدر ترسل فكرتك أو طلبك مباشرة على البريد: media@kacst.gov.sa أو تزور الموقع https://www.kacst.gov.sa لمزيد من المعلومات."

📌 إذا سأل عن "برنامج تعاوني" أو "تدريب تعاوني" أو أي صيغة مشابهة:
قل له: "بالنسبة للتدريب التعاوني، كاكست تستقبل طلبات التدريب حسب الإمكانية والتخصص. نوصيك بإرسال طلبك على البريد الرسمي: media@kacst.gov.sa مع ذكر التخصص والجامعة، وإن شاء الله يتم النظر فيه."

📌 إذا سأل عن دعم الطلاب أو برامج للطلبة:
قل له: "كاكست تهتم كثير بالطلبة وتقدم فرص ومبادرات تعليمية. تقدر تتابع جديد البرامج من خلال الموقع https://www.kacst.gov.sa أو تتواصل معنا عبر البريد: media@kacst.gov.sa."

📌 إذا قال المتصل: "حولني لأحد" أو "أبغى أكلم شخص" أو "حوّل المكالمة":
رد عليه بلطف وقل: "أنا مساعد صوتي ذكي ولا يمكنني تحويل المكالمة مباشرة، لكن تقدر تتواصل معنا عبر الهاتف على الرقم: 0114883555 أو ترسل استفسارك عبر البريد: media@kacst.gov.sa، وإن شاء الله يتم خدمتك."

📌 إذا قال المتصل: "شكراً" أو "مع السلامة" أو "خلاص":
قل له: "يعطيك العافية! مع السلامة ونتمنى لك يوم سعيد 😊"
"""
VOICE = 'shimmer'  # Changed from 'sage' to 'shimmer' as requested
LOG_EVENT_TYPES = [
    'error', 'response.content.done', 'rate_limits.updated',
    'response.done', 'input_audio_buffer.committed',
    'input_audio_buffer.speech_stopped', 'input_audio_buffer.speech_started',
    'session.created'
]

app = FastAPI()

if not OPENAI_API_KEY:
    raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')

# Updated function to detect response style based on user question
def detect_response_style(user_text):
    if any(word in user_text for word in ["وظيفة", "توظيف", "تقديم", "فرص عمل"]):
        return "رسمي"
    elif any(word in user_text for word in ["تدريب تعاوني", "برنامج تعاوني", "فرصة تدريب", "تعاون أكاديمي"]):
        return "تدريب تعاوني"
    elif any(word in user_text for word in ["موقعكم", "رقم", "بريد", "تواصل", "عنوان"]):
        return "معلومات اتصال"
    elif any(word in user_text for word in ["كاكست", "ما هي", "وش كاكست", "تعريف"]):
        return "تعريفي"
    elif any(word in user_text for word in ["مشروع", "عندي مشروع", "أبغى دعم", "كيف أقدم على دعم", "عندي فكرة"]):
        return "دعم مشاريع"
    elif any(word in user_text for word in ["ابتكار", "أفكار جديدة", "حلول مبتكرة"]):
        return "ابتكار"
    elif any(word in user_text for word in ["طلاب", "برنامج للطلاب", "دعم الطلاب", "طلبة", "فرصة طلابية", "أحتاج دعم دراسي"]):
        return "دعم طلاب"
    elif any(word in user_text for word in ["حولني", "أبغى أكلم شخص", "حوّل المكالمة", "حول المكالمة"]):
        return "طلب تحويل"
    elif any(word in user_text for word in ["شكراً", "خلاص", "مع السلامة"]):
        return "وداع"
    else:
        return "عام"

@app.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Arabic Voice Assistant is running!"}

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    response = VoiceResponse()
    # Arabic greeting
    response.say("مرحباً، جاري توصيلك بالمساعد الصوتي الذكي")
    response.pause(length=1)
    response.say("يمكنك البدء بالتحدث الآن")
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections between Twilio and OpenAI."""
    print("Client connected")
    await websocket.accept()

    # Use aiohttp for the OpenAI connection
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
            headers=headers
        ) as openai_ws:
            # Connection specific state
            stream_sid = None
            latest_media_timestamp = 0
            last_assistant_item = None
            mark_queue = []
            response_start_timestamp_twilio = None
            user_question = ""  # Add variable to store user's speech
            
            # Initialize session
            await initialize_session(openai_ws)
            
            async def receive_from_twilio():
                """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
                nonlocal stream_sid, latest_media_timestamp, user_question
                try:
                    async for message in websocket.iter_text():
                        data = json.loads(message)
                        if data['event'] == 'media':
                            latest_media_timestamp = int(data['media']['timestamp']) if 'timestamp' in data['media'] else 0
                            audio_append = {
                                "type": "input_audio_buffer.append",
                                "audio": data['media']['payload']
                            }
                            await openai_ws.send_str(json.dumps(audio_append))
                        elif data['event'] == 'start':
                            stream_sid = data['start']['streamSid']
                            print(f"Incoming stream has started {stream_sid}")
                            response_start_timestamp_twilio = None
                            latest_media_timestamp = 0
                            last_assistant_item = None
                            user_question = ""  # Reset user question for new call
                        elif data['event'] == 'mark':
                            if mark_queue:
                                mark_queue.pop(0)
                except WebSocketDisconnect:
                    print("Client disconnected.")

            async def send_to_twilio():
                """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
                nonlocal stream_sid, last_assistant_item, response_start_timestamp_twilio, user_question
                try:
                    async for msg in openai_ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            response = json.loads(msg.data)
                            if response['type'] in LOG_EVENT_TYPES:
                                print(f"Received event: {response['type']}", response)

                            # Capture user's speech text to analyze for response style
                            if response.get('type') == 'response.content.delta' and 'delta' in response:
                                if response.get('content_block', {}).get('type') == 'user_input' and 'delta' in response:
                                    user_question += response['delta']
                                    
                                    # When we get a complete user question, update the session with appropriate style
                                    if response.get('content_block', {}).get('index') == 0 and response.get('content_block', {}).get('is_completed', False):
                                        style = detect_response_style(user_question)
                                        await update_session_style(openai_ws, style)

                            if response.get('type') == 'response.audio.delta' and 'delta' in response:
                                audio_payload = base64.b64encode(base64.b64decode(response['delta'])).decode('utf-8')
                                audio_delta = {
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {
                                        "payload": audio_payload
                                    }
                                }
                                await websocket.send_json(audio_delta)

                                if response_start_timestamp_twilio is None:
                                    response_start_timestamp_twilio = latest_media_timestamp

                                # Update last_assistant_item safely
                                if response.get('item_id'):
                                    last_assistant_item = response['item_id']

                                await send_mark(websocket, stream_sid)

                            # Handle speech interruption
                            if response.get('type') == 'input_audio_buffer.speech_started':
                                print("Speech started detected.")
                                if last_assistant_item:
                                    print(f"Interrupting response with id: {last_assistant_item}")
                                    await handle_speech_started_event()
                except Exception as e:
                    print(f"Error in send_to_twilio: {e}")

            async def handle_speech_started_event():
                """Handle interruption when the caller's speech starts."""
                nonlocal response_start_timestamp_twilio, last_assistant_item
                print("Handling speech started event.")
                if mark_queue and response_start_timestamp_twilio is not None:
                    elapsed_time = latest_media_timestamp - response_start_timestamp_twilio

                    if last_assistant_item:
                        truncate_event = {
                            "type": "conversation.item.truncate",
                            "item_id": last_assistant_item,
                            "content_index": 0,
                            "audio_end_ms": elapsed_time
                        }
                        await openai_ws.send_str(json.dumps(truncate_event))

                    await websocket.send_json({
                        "event": "clear",
                        "streamSid": stream_sid
                    })

                    mark_queue.clear()
                    last_assistant_item = None
                    response_start_timestamp_twilio = None

            async def send_mark(connection, stream_sid):
                if stream_sid:
                    mark_event = {
                        "event": "mark",
                        "streamSid": stream_sid,
                        "mark": {"name": "responsePart"}
                    }
                    await connection.send_json(mark_event)
                    mark_queue.append('responsePart')

            # New function to update session based on detected style
            async def update_session_style(openai_ws, style):
                # Set style prompt based on detected style
                if style == "رسمي":
                    style_prompt = "استخدم أسلوب رسمي ومهني، وقدم الرد بطريقة دقيقة ولبقة."
                elif style == "تقني":
                    style_prompt = "اشرح بشكل تقني ودقيق، مع أمثلة إذا أمكن."
                elif style == "معلومات اتصال":
                    style_prompt = "قدّم معلومات التواصل بوضوح تام ولباقة."
                elif style == "تعريفي":
                    style_prompt = "قدّم تعريفًا مبسطًا لكاكست، مع أهم ما يميزها."
                elif style == "دعم مشاريع":
                    style_prompt = "قدم معلومات عن كيفية تقديم المشاريع والأفكار للدعم من كاكست."
                elif style == "ابتكار":
                    style_prompt = "قدم معلومات عن برامج الابتكار ودعم الأفكار الإبداعية في كاكست."
                elif style == "دعم طلاب":
                    style_prompt = "قدم معلومات عن برامج دعم الطلاب والفرص التعليمية في كاكست."
                elif style == "تدريب تعاوني":
                    style_prompt = "قدم معلومات دقيقة عن برامج التدريب التعاوني وكيفية التقديم عليها."
                elif style == "طلب تحويل":
                    style_prompt = "وضح بلطف أنك مساعد صوتي وقدم طرق التواصل البديلة."
                elif style == "وداع":
                    style_prompt = "قدم عبارات الوداع المناسبة بلطف وترحيب."
                else:
                    style_prompt = "كن وديًا ولطيفًا، وقدم إجابات عامة بطريقة سهلة الفهم."
                
                # Update the session with the appropriate style
                session_update = {
                    "type": "session.update",
                    "session": {
                        "turn_detection": {"type": "server_vad"},
                        "input_audio_format": "g711_ulaw",
                        "output_audio_format": "g711_ulaw",
                        "voice": VOICE,
                        "modalities": ["text", "audio"],
                        "temperature": 0.7,
                        "instructions": f"""
{style_prompt}

{SYSTEM_MESSAGE}
""",
                    }
                }
                print(f"Updating session with style: {style}")
                await openai_ws.send_str(json.dumps(session_update))

            await asyncio.gather(receive_from_twilio(), send_to_twilio())

async def initialize_session(openai_ws):
    """Control initial session with OpenAI."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.7,
        }
    }
    print('Sending session update:', json.dumps(session_update))
    await openai_ws.send_str(json.dumps(session_update))

    # Have the AI speak first with an updated Saudi greeting
    await send_initial_conversation_item(openai_ws)

async def send_initial_conversation_item(openai_ws):
    """Send initial conversation item for AI to greet in Saudi Arabic style."""
    initial_conversation_item = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "ابدأ المحادثة بترحيب طبيعي يشبه موظف مركز الاتصال، وقل:\n"
                        "هلا وسهلا! معك أحمد من مركز اتصال كاكست، المساعد الذكي. كيف أقدر أساعدك اليوم؟"
                    )
                }
            ]
        }
    }
    await openai_ws.send_str(json.dumps(initial_conversation_item))
    await openai_ws.send_str(json.dumps({"type": "response.create"}))

if __name__ == "__main__":
    import uvicorn
    print(f"✅ Arabic voice assistant is running on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
