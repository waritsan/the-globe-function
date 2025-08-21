
import os
import azure.functions as func
import logging
import json
import hmac
import hashlib
import base64
import requests
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import ListSortOrder



# In-memory user-to-thread mapping (for demo; use persistent storage for production)
user_thread_map = {}

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# New route to handle LINE webhook
@app.route(route="line_webhook", methods=["POST"])
def line_webhook(req: func.HttpRequest) -> func.HttpResponse:
    # Verify signature
    signature = req.headers.get("X-Line-Signature")
    body = req.get_body()
    if not LINE_CHANNEL_SECRET:
        return func.HttpResponse("LINE_CHANNEL_SECRET is not set in environment.", status_code=500)
    hash = hmac.new(LINE_CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    expected_signature = base64.b64encode(hash).decode()
    if signature != expected_signature:
        return func.HttpResponse("Invalid signature", status_code=403)

    try:
        events = json.loads(body.decode("utf-8")).get("events", [])
        responses = []
        for event in events:
            if event["type"] == "message" and event["message"]["type"] == "text":
                user_message = event["message"]["text"]
                reply_token = event["replyToken"]
                user_id = event["source"].get("userId")

                # Chat history: get or create thread for user
                foundry_response = None
                try:
                    project = AIProjectClient(
                        credential=DefaultAzureCredential(),
                        endpoint="https://the-globe-dev-resource.services.ai.azure.com/api/projects/the-globe-dev")
                    agent = project.agents.get_agent("asst_ADU10cnt6Gom8dd6ULoFwKqI")
                    thread_id = user_thread_map.get(user_id)
                    if thread_id:
                        thread = project.agents.threads.get(thread_id)
                    else:
                        thread = project.agents.threads.create()
                        user_thread_map[user_id] = thread.id

                    project.agents.messages.create(
                        thread_id=thread.id,
                        role="user",
                        content=user_message
                    )
                    run = project.agents.runs.create_and_process(
                        thread_id=thread.id,
                        agent_id=agent.id)
                    if run.status == "failed":
                        foundry_response = "Sorry, something went wrong."
                    else:
                        messages = project.agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
                        # Find the latest assistant message
                        assistant_messages = [m for m in messages if m.role == "assistant" and m.text_messages]
                        if assistant_messages:
                            foundry_response = assistant_messages[-1].text_messages[-1].text.value
                except Exception as e:
                    foundry_response = "Error: " + str(e)

                # Reply to LINE
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
                }
                reply_body = {
                    "replyToken": reply_token,
                    "messages": [{"type": "text", "text": foundry_response or "No response."}]
                }
                r = requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, data=json.dumps(reply_body))
                responses.append({"user_message": user_message, "foundry_response": foundry_response, "line_status": r.status_code})
        return func.HttpResponse(json.dumps({"results": responses}), status_code=200, mimetype="application/json")
    except Exception as e:
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")

@app.route(route="http_trigger")
def http_trigger(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    name = req.params.get('name')
    if not name:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            name = req_body.get('name')

    if name:
        return func.HttpResponse(f"Hello, {name}. This HTTP triggered function executed successfully.")
    else:
        return func.HttpResponse(
             "*This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
             status_code=200
        )


# New route to connect to AI Foundry
@app.route(route="ai_foundry")
def ai_foundry_trigger(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # Get user input from query string or request body
        user_input = req.params.get("message")
        if not user_input:
            try:
                req_body = req.get_json()
                user_input = req_body.get("message")
            except Exception:
                user_input = None

        if not user_input:
            return func.HttpResponse("No message provided.", status_code=400)

        project = AIProjectClient(
            credential=DefaultAzureCredential(),
            endpoint="https://the-globe-dev-resource.services.ai.azure.com/api/projects/the-globe-dev")

        agent = project.agents.get_agent("asst_ADU10cnt6Gom8dd6ULoFwKqI")
        thread = project.agents.threads.create()
        message = project.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_input
        )
        run = project.agents.runs.create_and_process(
            thread_id=thread.id,
            agent_id=agent.id)

        if run.status == "failed":
            return func.HttpResponse(
                json.dumps({"error": run.last_error}),
                status_code=500,
                mimetype="application/json"
            )
        else:
            messages = project.agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
            chat = []
            for message in messages:
                if message.text_messages:
                    chat.append({
                        "role": message.role,
                        "text": message.text_messages[-1].text.value
                    })
            return func.HttpResponse(
                json.dumps({"messages": chat}),
                status_code=200,
                mimetype="application/json"
            )
    except Exception as e:
        logging.error(f"AI Foundry error: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )