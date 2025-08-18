import azure.functions as func
import logging

import json

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import ListSortOrder

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

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