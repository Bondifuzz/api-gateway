from aiohttp import web
from black import json


async def index(request: web.Request):
    return web.Response(
        text="Jira reporter stub is running",
        content_type="text/html",
        charset="utf-8",
    )


async def create_integration(request: web.Request):

    json_data = await request.json()
    json_data["url"]
    json_data["project"]
    json_data["username"]
    json_data["password"]
    json_data["issue_type"]
    json_data["priority"]
    json_data["update_rev"]

    return web.json_response(
        {
            "status": "OK",
            "result": {
                "key": "89221",
            },
        },
        status=202,
    )

    # return web.json_response(
    #     {
    #         "status": "Failed",
    #         "error": "Some error",
    #     },
    #     status=422,
    # )


async def get_integration(request: web.Request):

    match_info = request.match_info
    integration_id = match_info["id"]

    return web.json_response(
        {
            "status": "OK",
            "result": {
                "id": integration_id,
                "url": "str",
                "project": "my_project",
                "username": "user_bob",
                "password": "password_bob",
                "issue_type": "Task",
                "priority": "Normal",
            },
        },
        status=200,
    )


async def update_integration(request: web.Request):

    json_data = await request.json()
    match_info = request.match_info
    integration_id = match_info["id"]

    json_data["url"]
    json_data["project"]
    json_data["username"]
    json_data["password"]
    json_data["issue_type"]
    json_data["priority"]
    json_data["update_rev"]

    return web.json_response({
        "status": "OK",
        "result": {
            "old": {
                "url": "str",
                "project": "my_project",
                "username": "user_bob",
                "password": "password_bob",
                "issue_type": "Task",
                "priority": "Normal",
            },
            "new": json_data,
        }
    }, status=202)


async def delete_integration(request: web.Request):
    match_info = request.match_info
    integration_id = match_info["id"]
    return web.json_response({}, status=204)


def run():

    routes = [
        web.get("/", index),
        web.post("/api/v1/integrations", create_integration),
        web.get("/api/v1/integrations/{id}", get_integration),
        web.put("/api/v1/integrations/{id}", update_integration),
        web.delete("/api/v1/integrations/{id}", delete_integration),
    ]

    app = web.Application()
    app.add_routes(routes)

    host = "0.0.0.0"
    port = "8089"
    web.run_app(app, host=host, port=port, access_log=None)

if __name__ == "__main__":
    run()