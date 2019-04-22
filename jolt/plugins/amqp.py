import click
import pika
import uuid
import keyring
import getpass


from jolt.cli import cli
from jolt import config
from jolt import scheduler
from jolt import utils
from jolt import log
from jolt.manifest import JoltManifest
from jolt.tools import Tools
from jolt.error import JoltCommandError


NAME = "amqp"


def _get_auth():
    service = config.get(NAME, "keyring.service", NAME)

    username = config.get(NAME, "keyring.username")
    if not username:
        return "guest", "guest"

    password = config.get(NAME, "keyring.password") or \
               keyring.get_password(NAME, username)
    if not password:
        password = getpass.getpass(NAME + " password: ")
        assert password, "no password in keyring for " + NAME
        keyring.set_password(service, username, password)
    return username, password


def _get_connection():
    host = config.get("amqp", "host", "amqp-service")
    port = int(config.get("amqp", "port", 5672))
    username, password = _get_auth()
    credentials = pika.PlainCredentials(username, password)
    return pika.BlockingConnection(
        pika.ConnectionParameters(
            host=host,
            port=port,
            credentials=credentials))


TYPE = "Remote execution"
TIMEOUT = (3.5, 27)
POLL_INTERVAL = 1


@cli.command(name="amqp-worker", hidden=True)
@click.pass_context
def amqp_worker(ctx):
    """ Run an AMQP worker """

    connection = _get_connection()
    channel = connection.channel()
    channel.queue_declare(queue='jolt_task_queue')

    tools = Tools()

    def on_request(ch, method, props, body):
        log.info("Received execution request")
        print(body)

        with open("default.joltxmanifest", "wb") as f:
            f.write(body)

        log.info("Manifest written")

        for recipe in tools.glob("*.jolt"):
            tools.unlink(recipe)

        log.info("Running jolt")

        try:
            tools.run("jolt -vv build --worker")
        except JoltCommandError as e:
            response = ["FAILED"]
            response.extend(e.stdout)
            response.extend(e.stderr)
            response = "\n".join(response)
            log.error("Task failed")
        except Exception as e:
            response = "FAILED"
            log.error("Task failed")
        else:
            response = "SUCCESS\n"
            log.info("Task succeeded")

        ch.basic_publish(
            exchange='',
            routing_key=props.reply_to,
            properties=pika.BasicProperties(correlation_id = props.correlation_id),
            body=str(response))

        log.info("Result published")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='jolt_task_queue', on_message_callback=on_request)

    log.info("Service started")
    channel.start_consuming()


class AmqpExecutor(scheduler.NetworkExecutor):

    def on_response(self, ch, method, props, body):
        if self.corr_id == props.correlation_id:
            self.response = body.decode()

    def __init__(self, factory, task):
        super(AmqpExecutor, self).__init__(factory)
        self.factory = factory
        self.task = task

        self.connection = _get_connection()
        self.channel = self.connection.channel()
        result = self.channel.queue_declare('', exclusive=True)
        self.callback_queue = result.method.queue
        self.channel.basic_consume(
            queue=self.callback_queue,
            on_message_callback=self.on_response,
            auto_ack=True)

    def _run(self, env):
        manifest = JoltManifest.export(self.task)
        build = manifest.create_build()

        tasks = [self.task.qualified_name]
        tasks += [t.qualified_name for t in self.task.extensions]

        for task in tasks:
            mt = build.create_task()
            mt.name = self.task.qualified_name

        for task in self.factory.options.default:
            default = build.create_default()
            default.name = task

        self.response = None
        self.corr_id = str(uuid.uuid4())
        self.channel.basic_publish(
            exchange='',
            routing_key='jolt_task_queue',
            properties=pika.BasicProperties(
                reply_to=self.callback_queue,
                correlation_id=self.corr_id,
            ),
            body=manifest.format())

        log.verbose("[AMQP] Queued {0}", self.task.qualified_name)

        self.task.running()
        for extension in self.task.extensions:
            extension.running()

        while self.response is None:
            self.connection.process_data_events()

        log.verbose("[AMQP] Finished {0}", self.task.qualified_name)

        result = self.response.splitlines()
        output = result[1:]
        result = result[0]

        if result[0] != "SUCCESS":
            for line in output:
                log.transfer(line, self.task.identity[:8])
            assert result == "SUCCESS", \
                "[AMQP] remote build failed with status: {0}".format(result)

        assert env.cache.is_available_remotely(self.task), \
            "[AMQP] no artifact produced for {0}, check configuration"\
            .format(self.task.qualified_name)

        assert env.cache.download(self.task) or \
            not env.cache.download_enabled(), \
            "[AMQP] failed to download artifact for {0}"\
            .format(self.task.qualified_name)

        for extension in self.task.extensions:
            assert env.cache.download(extension) or \
                not env.cache.download_enabled(), \
                "[AMQP] failed to download artifact for {0}"\
                .format(extension.qualified_name)

        return self.task

    def run(self, env):
        try:
            self.task.started(TYPE)
            for extension in self.task.extensions:
                extension.started(TYPE)
            self._run(env)
            for extension in self.task.extensions:
                extension.finished(TYPE)
            self.task.finished(TYPE)
        except Exception as e:
            log.exception()
            for extension in self.task.extensions:
                extension.failed(TYPE)
            self.task.failed(TYPE)
            raise e
        return self.task


@scheduler.ExecutorFactory.Register
class AmqpExecutorFactory(scheduler.NetworkExecutorFactory):
    def __init__(self, options):
        super(AmqpExecutorFactory, self).__init__(max_workers=16)
        self._options = options

    @property
    def options(self):
        return self._options

    def create(self, task):
        return AmqpExecutor(self, task)



log.verbose("AMQP loaded")
