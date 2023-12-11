from jolt import cache
from jolt import cli
from jolt import config
from jolt import graph
from jolt import log
from jolt import scheduler
from jolt.manifest import JoltManifest
from jolt.options import JoltOptions
from jolt.tasks import TaskRegistry
from jolt.tools import Tools

import click
import getpass
import keyring
import requests
import urllib3
import json

urllib3.disable_warnings()


NAME = "snap"


def _get_auth():
    service = config.get(NAME, "keyring.service", "jenkins")
    username = config.get(NAME, "keyring.username") or \
        input("Jenkins username: ")
    if username:
        config.set(NAME, "keyring.username", username)
        config.save()
    password = config.get(NAME, "keyring.password") or \
        keyring.get_password(service, username)
    if not password:
        password = getpass.getpass("Jenkins password: ")
        assert password, "no password in keyring for " + service
        keyring.set_password(service, username, password)
    return username, password


@cli.cli.command(name="snap")
@click.argument("task", type=str, required=True, shell_complete=cli._autocomplete_tasks)
@click.option("-d", "--default", type=str, multiple=True, help="Override default parameter values.")
@click.pass_context
def snap(ctx, task, default):
    """ Submit a task for background build in a Jenkins job """

    manifest = ctx.obj["manifest"]
    options = JoltOptions(default=default)
    acache = cache.ArtifactCache.get(options)
    registry = TaskRegistry.get()

    for params in default:
        registry.set_default_parameters(params)

    gb = graph.GraphBuilder(registry, acache, manifest, options, progress=True)
    dag = gb.build([task])

    manifest = JoltManifest.export(dag.requested_goals)
    manifest.config = ""
    build = manifest.create_build()

    for task in dag.goals:
        mt = build.create_task()
        mt.name = task.qualified_name

    for task in options.default:
        default = build.create_default()
        default.name = task

    registry = scheduler.ExecutorRegistry.get()
    for key, value in registry.get_network_parameters(dag.requested_goals[0]).items():
        param = manifest.create_parameter()
        param.key = key
        param.value = value

    url = config.get("snap", "url")

    jolt_id = manifest.get_parameter("jolt_identity")
    jolt_url = manifest.get_parameter("jolt_url")

    params = {
        "parameter": [
            {
                "name": "default.joltxmanifest",
                "file": "file0",
            },
            {
                "name": "jolt.config",
                "file": "file1",
            },
            {
                "name": "JOLT_TASK",
                "value": dag.requested_goals[0].qualified_name,
            },
            {
                "name": "JOLT",
                "value": jolt_id,
            },
            {
                "name": "JOLT_URL",
                "value": jolt_url,
            },
            {
                "name": "JOLT_NOTIFY",
                "value": config.get(NAME, "notify", ""),
            },
        ]
    }

    tools = Tools()
    data, content_type = urllib3.encode_multipart_formdata([
        ("file0", ("default.joltxmanifest", manifest.format())),
        ("file1", ("jolt.config", tools.read_file(config.location))),
        ("json", json.dumps(params)),
        ("Submit", "Build"),
    ])

    resp = requests.post(url + "/build", auth=_get_auth(), data=data,
                         headers={"content-type": content_type}, verify=False)
    resp.raise_for_status()
    log.info("Build successfully submitted")
