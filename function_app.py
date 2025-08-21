
import azure.functions as func
import logging
import json
import hmac
import hashlib
import base64
import requests
LINE_CHANNEL_ACCESS_TOKEN = "nw055XPBSkjEVcAzIM5FX3Qj4IZCRkhmruhCWwks7aU1HNoq/dRlNN/5esHx3uJi6Pe+nRfm7Db1/l8y90aAOpf3yCbAYFNPaV8mYgj+5tzRryHR9459hLjD7bCw7cODgTm2JUKjaCnsNaJ1CMdAFwdB04t89/1O/w1cDnyilFU="
LINE_CHANNEL_SECRET = "69db4b6fbe5c360d8c872bc067b47b0f"

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import ListSortOrder


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# New route to handle LINE webhook
@app.route(route="line_webhook", methods=["POST"])
def line_webhook(req: func.HttpRequest) -> func.HttpResponse:
    # Verify signature
    signature = req.headers.get("X-Line-Signature")
    body = req.get_body()
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

                # Call Azure Foundry
                foundry_response = None
                try:
                    project = AIProjectClient(
                        credential=DefaultAzureCredential(),
                        endpoint="https://the-globe-dev-resource.services.ai.azure.com/api/projects/the-globe-dev")
                    agent = project.agents.get_agent("asst_ADU10cnt6Gom8dd6ULoFwKqI")
                    thread = project.agents.threads.create()
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
                        # Only reply with the agent's response
                        for message in messages:
                            if message.role == "assistant" and message.text_messages:
                                foundry_response = message.text_messages[-1].text.value
                                break
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