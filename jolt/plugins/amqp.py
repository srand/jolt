import click
import functools
import getpass
import keyring
import os
import pika
from pika.exceptions import AMQPConnectionError
from pika.adapters.utils.connection_workflow import AMQPConnectorStackTimeout
import threading
import time

from jolt.cli import cli
from jolt import config
from jolt import filesystem as fs
from jolt import hooks
from jolt import log
from jolt import scheduler
from jolt import utils
from jolt.manifest import JoltManifest
from jolt.tools import Tools
from jolt.error import JoltCommandError
from jolt.error import raise_error
from jolt.error import raise_task_error_if
from jolt.error import raise_task_error_on_exception


NAME = "amqp"


def _get_auth():
    service = config.get(NAME, "keyring.service", NAME)

    username = config.get(NAME, "keyring.username")
    if not username:
        return "guest", "guest"

    password = config.get(NAME, "keyring.password") or keyring.get_password(NAME, username)
    if not password:
        password = getpass.getpass(NAME + " password: ")
        assert password, "no password in keyring for " + NAME
        keyring.set_password(service, username, password)
    return username, password


def _get_url():
    host = config.get("amqp", "host", "amqp-service")
    port = int(config.get("amqp", "port", 5672))
    username, password = _get_auth()
    return "amqp://{}:{}@{}:{}/%2F".format(username, password, host, port)


TYPE = "Remote execution"
TIMEOUT = (3.5, 27)
POLL_INTERVAL = 1


class WorkerTaskConsumer(object):
    """This is a task consumer that will handle unexpected interactions
    with RabbitMQ such as channel and connection closures.

    If RabbitMQ closes the connection, this class will stop and indicate
    that reconnection is necessary. You should look at the output, as
    there are limited reasons why the connection may be closed, which
    usually are tied to permission related issues or socket timeouts.

    If the channel is closed, it will indicate a problem with one of the
    commands that were issued and that should surface in the output as well.

    """
    EXCHANGE = 'jolt_exchange'
    EXCHANGE_TYPE = 'direct'
    QUEUE = 'jolt_tasks'
    RESULT_EXCHANGE = 'jolt_results'
    ROUTING_KEY_PREFIX = ''
    ROUTING_KEY_REQUEST = 'default'
    ROUTING_KEY_RESULT = 'default'

    def __init__(self, amqp_url):
        """Create a new instance of the consumer class, passing in the AMQP
        URL used to connect to RabbitMQ.

        :param str amqp_url: The AMQP url to connect with

        """
        self.should_reconnect = False
        self.was_consuming = False

        self._connection = None
        self._channel = None
        self._closing = False
        self._consumer_tag = None
        self._url = amqp_url
        self._consuming = False
        # In production, experiment with higher prefetch values
        # for higher consumer throughput
        self._prefetch_count = 1
        self._job = None
        self._routing_key = self.ROUTING_KEY_PREFIX + config.get(
            "amqp", "routing_key",
            os.getenv("RABBITMQ_ROUTING_KEY", self.ROUTING_KEY_REQUEST))
        self._queue = self.QUEUE + "_" + self._routing_key
        self._max_priority = config.getint("amqp", "max-priority", 1)

    def connect(self):
        """This method connects to RabbitMQ, returning the connection handle.
        When the connection is established, the on_connection_open method
        will be invoked by pika.

        :rtype: pika.SelectConnection

        """
        log.info('Connecting to {}', self._url)
        return pika.SelectConnection(
            parameters=pika.URLParameters(self._url),
            on_open_callback=self.on_connection_open,
            on_open_error_callback=self.on_connection_open_error,
            on_close_callback=self.on_connection_closed)

    def close_connection(self):
        self._consuming = False
        if self._connection.is_closing or self._connection.is_closed:
            log.info('Connection is closing or already closed')
        else:
            log.info('Closing connection')
            self._connection.close()

    def on_connection_open(self, _unused_connection):
        """This method is called by pika once the connection to RabbitMQ has
        been established. It passes the handle to the connection object in
        case we need it, but in this case, we'll just mark it unused.

        :param pika.SelectConnection _unused_connection: The connection

        """
        log.info('Connection opened')
        self.open_channel()

    def on_connection_open_error(self, _unused_connection, err):
        """This method is called by pika if the connection to RabbitMQ
        can't be established.

        :param pika.SelectConnection _unused_connection: The connection
        :param Exception err: The error

        """
        log.error('Connection open failed: {}', err)
        self.reconnect()

    def on_connection_closed(self, _unused_connection, reason):
        """This method is invoked by pika when the connection to RabbitMQ is
        closed unexpectedly. Since it is unexpected, we will reconnect to
        RabbitMQ if it disconnects.

        :param pika.connection.Connection connection: The closed connection obj
        :param Exception reason: exception representing reason for loss of
            connection.

        """
        self._channel = None
        if self._closing:
            self._connection.ioloop.stop()
        else:
            log.warning('Connection closed, reconnect necessary: {}', reason)
            self.reconnect()

    def reconnect(self):
        """Will be invoked if the connection can't be opened or is
        closed. Indicates that a reconnect is necessary then stops the
        ioloop.

        """
        self.should_reconnect = True
        self.stop()

    def open_channel(self):
        """Open a new channel with RabbitMQ by issuing the Channel.Open RPC
        command. When RabbitMQ responds that the channel is open, the
        on_channel_open callback will be invoked by pika.

        """
        log.info('Creating a new channel')
        self._connection.channel(on_open_callback=self.on_channel_open)

    def on_channel_open(self, channel):
        """This method is invoked by pika when the channel has been opened.
        The channel object is passed in so we can make use of it.

        Since the channel is now open, we'll declare the exchange to use.

        :param pika.channel.Channel channel: The channel object

        """
        log.info('Channel opened')
        self._channel = channel
        self.add_on_channel_close_callback()
        self.setup_exchange(self.EXCHANGE)

    def add_on_channel_close_callback(self):
        """This method tells pika to call the on_channel_closed method if
        RabbitMQ unexpectedly closes the channel.

        """
        log.info('Adding channel close callback')
        self._channel.add_on_close_callback(self.on_channel_closed)

    def on_channel_closed(self, channel, reason):
        """Invoked by pika when RabbitMQ unexpectedly closes the channel.
        Channels are usually closed if you attempt to do something that
        violates the protocol, such as re-declare an exchange or queue with
        different parameters. In this case, we'll close the connection
        to shutdown the object.

        :param pika.channel.Channel: The closed channel
        :param Exception reason: why the channel was closed

        """
        log.warning('Channel {} was closed: {}', channel, reason)
        self.close_connection()

    def setup_exchange(self, exchange_name):
        """Setup the exchange on RabbitMQ by invoking the Exchange.Declare RPC
        command. When it is complete, the on_exchange_declareok method will
        be invoked by pika.

        :param str|unicode exchange_name: The name of the exchange to declare

        """
        log.info('Declaring exchange: {}', exchange_name)
        # Note: using functools.partial is not required, it is demonstrating
        # how arbitrary data can be passed to the callback when it is called
        cb = functools.partial(
            self.on_exchange_declareok, userdata=exchange_name)
        self._channel.exchange_declare(
            exchange=exchange_name,
            exchange_type=self.EXCHANGE_TYPE,
            callback=cb)

    def on_exchange_declareok(self, _unused_frame, userdata):
        """Invoked by pika when RabbitMQ has finished the Exchange.Declare RPC
        command.

        :param pika.Frame.Method unused_frame: Exchange.DeclareOk response frame
        :param str|unicode userdata: Extra user data (exchange name)

        """
        log.info('Exchange declared: {}', userdata)
        self.setup_queue(self._queue)

    def setup_queue(self, queue_name):
        """Setup the queue on RabbitMQ by invoking the Queue.Declare RPC
        command. When it is complete, the on_queue_declareok method will
        be invoked by pika.

        :param str|unicode queue_name: The name of the queue to declare.

        """
        log.info('Declaring queue {}', queue_name)
        cb = functools.partial(self.on_queue_declareok, userdata=queue_name)
        self._channel.queue_declare(
            queue=queue_name, callback=cb,
            arguments={
                "x-message-deduplication": True,
                "x-max-priority": self._max_priority
            })

    def on_queue_declareok(self, _unused_frame, userdata):
        """Method invoked by pika when the Queue.Declare RPC call made in
        setup_queue has completed. In this method we will bind the queue
        and exchange together with the routing key by issuing the Queue.Bind
        RPC command. When this command is complete, the on_bindok method will
        be invoked by pika.

        :param pika.frame.Method _unused_frame: The Queue.DeclareOk frame
        :param str|unicode userdata: Extra user data (queue name)

        """
        queue_name = userdata
        log.info('Binding {} to {} with {}',
                 self.EXCHANGE, queue_name, self._routing_key)
        cb = functools.partial(self.on_bindok, userdata=queue_name)
        self._channel.queue_bind(
            queue_name,
            self.EXCHANGE,
            routing_key=self._routing_key,
            callback=cb)
        log.info('Binding {} to {} with jolt_{}',
                 self.EXCHANGE, queue_name, self._routing_key)
        self._channel.queue_bind(
            queue_name,
            self.EXCHANGE,
            routing_key="jolt_" + self._routing_key)

    def on_bindok(self, _unused_frame, userdata):
        """Invoked by pika when the Queue.Bind method has completed. At this
        point we will set the prefetch count for the channel.

        :param pika.frame.Method _unused_frame: The Queue.BindOk response frame
        :param str|unicode userdata: Extra user data (queue name)

        """
        log.info('Queue bound: {}', userdata)
        self.set_qos()

    def set_qos(self):
        """This method sets up the consumer prefetch to only be delivered
        one message at a time. The consumer must acknowledge this message
        before RabbitMQ will deliver another one. You should experiment
        with different prefetch values to achieve desired performance.

        """
        self._channel.basic_qos(
            prefetch_count=self._prefetch_count, callback=self.on_basic_qos_ok)

    def on_basic_qos_ok(self, _unused_frame):
        """Invoked by pika when the Basic.QoS method has completed. At this
        point we will start consuming messages by calling start_consuming
        which will invoke the needed RPC commands to start the process.

        :param pika.frame.Method _unused_frame: The Basic.QosOk response frame

        """
        log.info('QOS set to: {}', self._prefetch_count)
        self.start_consuming()

    def start_consuming(self):
        """This method sets up the consumer by first calling
        add_on_cancel_callback so that the object is notified if RabbitMQ
        cancels the consumer. It then issues the Basic.Consume RPC command
        which returns the consumer tag that is used to uniquely identify the
        consumer with RabbitMQ. We keep the value to use it when we want to
        cancel consuming. The on_message method is passed in as a callback pika
        will invoke when a message is fully received.

        """
        log.info('Issuing consumer related RPC commands')
        self.add_on_cancel_callback()
        self._consumer_tag = self._channel.basic_consume(
            self._queue, self.on_message)
        self.was_consuming = True
        self._consuming = True

    def add_on_cancel_callback(self):
        """Add a callback that will be invoked if RabbitMQ cancels the consumer
        for some reason. If RabbitMQ does cancel the consumer,
        on_consumer_cancelled will be invoked by pika.

        """
        log.info('Adding consumer cancellation callback')
        self._channel.add_on_cancel_callback(self.on_consumer_cancelled)

    def on_consumer_cancelled(self, method_frame):
        """Invoked by pika when RabbitMQ sends a Basic.Cancel for a consumer
        receiving messages.

        :param pika.frame.Method method_frame: The Basic.Cancel frame

        """
        log.info('Consumer was cancelled remotely, shutting down: {}',
                 method_frame)
        if self._channel:
            self._channel.close()

    def on_message(self, channel, basic_deliver, properties, body):
        """Invoked by pika when a message is delivered from RabbitMQ. The
        channel is passed for your convenience. The basic_deliver object that
        is passed in carries the exchange, routing key, delivery tag and
        a redelivered flag for the message. The properties passed in is an
        instance of BasicProperties with the message properties and the body
        is the message that was sent.

        :param pika.channel.Channel _unused_channel: The channel object
        :param pika.Spec.Basic.Deliver: basic_deliver method
        :param pika.Spec.BasicProperties: properties
        :param bytes body: The message body

        """
        log.info('Received execution request # {} from {}',
                 basic_deliver.delivery_tag, properties.app_id)

        class Job(threading.Thread):
            def __init__(self, consumer, channel, basic_deliver, properties, body):
                super(Job, self).__init__()
                self.consumer = consumer
                self.channel = channel
                self.basic_deliver = basic_deliver
                self.properties = properties
                self.body = body

            def selfdeploy(self):
                """ Installs the correct version of Jolt as specified in execution request. """

                tools = Tools()
                manifest = JoltManifest()
                try:
                    manifest.parse()
                    ident = manifest.get_parameter("jolt_identity")
                    url = manifest.get_parameter("jolt_url")
                    if not ident or not url:
                        return "jolt"

                    requires = manifest.get_parameter("jolt_requires")

                    log.info("Jolt version: {}", ident)

                    src = "build/selfdeploy/{}/src".format(ident)
                    env = "build/selfdeploy/{}/env".format(ident)

                    if not fs.path.exists(env):
                        try:
                            fs.makedirs(src)
                            tools.run("curl {} | tar zx -C {}", url, src)
                            tools.run("virtualenv {}", env)
                            tools.run(". {}/bin/activate && pip install -e {}", env, src)
                            if requires:
                                tools.run(". {}/bin/activate && pip install {}", env, requires)
                        except Exception as e:
                            tools.rmtree("build/selfdeploy/{}", ident, ignore_errors=True)
                            raise e

                    return ". {}/bin/activate && jolt".format(env)
                except Exception as e:
                    log.exception()
                    raise e

            def run(self):
                with open("default.joltxmanifest", "wb") as f:
                    f.write(self.body)

                log.info("Manifest written")

                tools = Tools()
                for recipe in tools.glob("*.jolt"):
                    tools.unlink(recipe)

                try:
                    jolt = self.selfdeploy()
                    config_file = config.get("amqp", "config", "")
                    if config_file:
                        config_file = "-c " + config_file

                    log.info("Running jolt")
                    tools.run("{} -vv {} build --worker --result result.joltxmanifest",
                              jolt, config_file, output_stdio=True)
                except JoltCommandError as e:
                    self.response = ""
                    try:
                        manifest = JoltManifest()
                        try:
                            manifest.parse("result.joltxmanifest")
                        except Exception:
                            manifest.duration = "0"
                        manifest.result = "FAILED"
                        manifest.stdout = "\n".join(e.stdout)
                        manifest.stderr = "\n".join(e.stderr)
                        self.response = manifest.format()
                    except Exception:
                        log.exception()
                    log.error("Task failed")
                except Exception:
                    log.exception()
                    self.response = ""
                    try:
                        manifest = JoltManifest()
                        try:
                            manifest.parse("result.joltxmanifest")
                        except Exception:
                            manifest.duration = "0"
                        manifest.result = "FAILED"
                        self.response = manifest.format()
                    except Exception:
                        log.exception()
                    log.error("Task failed")
                else:
                    self.response = ""
                    try:
                        manifest = JoltManifest()
                        try:
                            manifest.parse("result.joltxmanifest")
                        except Exception:
                            manifest.duration = "0"
                        manifest.result = "SUCCESS"
                        self.response = manifest.format()
                    except Exception:
                        log.exception()
                    log.info("Task succeeded")

                utils.call_and_catch(tools.unlink, "result.joltxmanifest")
                self.consumer.add_on_job_completed_callback(self)

        self._job = Job(self, channel, basic_deliver, properties, body)
        self._job.start()

    def add_on_job_completed_callback(self, job):
        if self._connection:
            self._connection.ioloop.add_callback_threadsafe(
                functools.partial(self.on_job_completed, job))
        else:
            self._job = None

    def on_job_completed(self, job):
        job.join()
        if job.channel is self._channel:
            self._channel.basic_publish(
                exchange=self.RESULT_EXCHANGE,
                routing_key=job.properties.correlation_id,
                properties=pika.BasicProperties(
                    correlation_id=job.properties.correlation_id,
                    expiration="600000"),
                body=str(job.response))

            self.acknowledge_message(job.basic_deliver.delivery_tag)
            log.info("Result published")
        else:
            log.info("Result not published as connection was lost")
        self._job = None

    def acknowledge_message(self, delivery_tag):
        """Acknowledge the message delivery from RabbitMQ by sending a
        Basic.Ack RPC method for the delivery tag.

        :param int delivery_tag: The delivery tag from the Basic.Deliver frame

        """
        log.info('Acknowledging message {}', delivery_tag)
        self._channel.basic_ack(delivery_tag)

    def stop_consuming(self):
        """Tell RabbitMQ that you would like to stop consuming by sending the
        Basic.Cancel RPC command.

        """
        if self._channel:
            log.info('Sending a Basic.Cancel RPC command to RabbitMQ')
            cb = functools.partial(
                self.on_cancelok, userdata=self._consumer_tag)
            self._channel.basic_cancel(self._consumer_tag, cb)

    def on_cancelok(self, _unused_frame, userdata):
        """This method is invoked by pika when RabbitMQ acknowledges the
        cancellation of a consumer. At this point we will close the channel.
        This will invoke the on_channel_closed method once the channel has been
        closed, which will in-turn close the connection.

        :param pika.frame.Method _unused_frame: The Basic.CancelOk frame
        :param str|unicode userdata: Extra user data (consumer tag)

        """
        self._consuming = False
        log.info(
            'RabbitMQ acknowledged the cancellation of the consumer: {}',
            userdata)
        self.close_channel()

    def close_channel(self):
        """Call to close the channel with RabbitMQ cleanly by issuing the
        Channel.Close RPC command.

        """
        log.info('Closing the channel')
        self._channel.close()

    def run(self):
        """Run the task consumer by connecting to RabbitMQ and then
        starting the IOLoop to block and allow the SelectConnection to operate.

        """
        self._connection = self.connect()
        self._connection.ioloop.start()

    def stop(self):
        """Cleanly shutdown the connection to RabbitMQ by stopping the consumer
        with RabbitMQ. When RabbitMQ confirms the cancellation, on_cancelok
        will be invoked by pika, which will then closing the channel and
        connection. The IOLoop is started again because this method is invoked
        when CTRL-C is pressed raising a KeyboardInterrupt exception. This
        exception stops the IOLoop which needs to be running for pika to
        communicate with RabbitMQ. All of the commands issued prior to starting
        the IOLoop will be buffered but not processed.

        """
        if not self._closing:
            self._closing = True
            log.info('Stopping')
            if self._consuming:
                self.stop_consuming()
                self._connection.ioloop.start()
            else:
                self._connection.ioloop.stop()
            log.info('Stopped')
            if self._job:
                self.on_job_completed(self._job)


class ReconnectingWorkerTaskConsumer(object):
    """This is a task consumer that will reconnect if the nested
    WorkerTaskConsumer indicates that a reconnect is necessary.

    """

    def __init__(self, amqp_url):
        self._reconnect_delay = 0
        self._amqp_url = amqp_url
        self._consumer = WorkerTaskConsumer(self._amqp_url)

    def run(self):
        while True:
            try:
                self._consumer.run()
            except KeyboardInterrupt:
                self._consumer.stop()
                break
            self._maybe_reconnect()

    def _maybe_reconnect(self):
        if self._consumer.should_reconnect:
            self._consumer.stop()
            reconnect_delay = self._get_reconnect_delay()
            log.info('Reconnecting after {} seconds', reconnect_delay)
            time.sleep(reconnect_delay)
            self._consumer = WorkerTaskConsumer(self._amqp_url)

    def _get_reconnect_delay(self):
        if self._consumer.was_consuming:
            self._reconnect_delay = 0
        else:
            self._reconnect_delay += 1
        if self._reconnect_delay > 30:
            self._reconnect_delay = 30
        return self._reconnect_delay


@cli.command(name="amqp-worker", hidden=True)
@click.pass_context
def amqp_worker(ctx):
    """ Run an AMQP worker """

    consumer = ReconnectingWorkerTaskConsumer(_get_url())
    log.info("Service started")
    consumer.run()


class AmqpExecutor(scheduler.NetworkExecutor):

    def __init__(self, factory, task):
        super(AmqpExecutor, self).__init__(factory)
        self.factory = factory
        self.callback_queue = None
        self.connection = None
        self.priority = config.getint("amqp", "priority", 0)
        self.task = task

    def _create_manifest(self):
        manifest = JoltManifest.export(self.task)
        build = manifest.create_build()

        tasks = [self.task.qualified_name]
        tasks += [t.qualified_name for t in self.task.extensions]

        for task in tasks:
            mt = build.create_task()
            mt.name = task

        registry = scheduler.ExecutorRegistry.get()
        for key, value in registry.get_network_parameters(self.task).items():
            param = manifest.create_parameter()
            param.key = key
            param.value = value

        routing_key = WorkerTaskConsumer.ROUTING_KEY_PREFIX
        routing_key += getattr(self.task.task, "routing_key", WorkerTaskConsumer.ROUTING_KEY_REQUEST)

        return manifest.format(), routing_key

    def _run(self, env):
        timeout = int(config.getint("amqp", "timeout", 300))
        manifest, routing_key = self._create_manifest()

        self.connect()
        self.publish_request(manifest, routing_key)

        log.debug("[AMQP] Queued {0}", self.task.short_qualified_name)

        self.task.running()
        for extension in self.task.extensions:
            extension.running()

        while self.response is None:
            try:
                self.connection.process_data_events(time_limit=timeout)
                if self.response is None:
                    self.task.info("Remote execution still in progress after {}",
                                   self.task.duration_queued)
            except (ConnectionError, AMQPConnectionError):
                log.warning("[AMQP] Lost server connection")
                self.connect()

        log.debug("[AMQP] Finished {0}", self.task.short_qualified_name)

        manifest = JoltManifest()
        with raise_task_error_on_exception(self.task, "failed to parse build result manifest"):
            manifest.parsestring(self.response)

        self.task.running(utils.duration() - float(manifest.duration))

        if manifest.result != "SUCCESS":
            output = []
            if manifest.stdout:
                output.extend(manifest.stdout.split("\n"))
            if manifest.stderr:
                output.extend(manifest.stderr.split("\n"))
            for line in output:
                log.transfer(line, self.task.identity[:8])
            for task in [self.task] + self.task.extensions:
                with task.task.report() as report:
                    remote_report = manifest.find_task(task.qualified_name)
                    if remote_report:
                        for error in remote_report.errors:
                            report.manifest.append(error)
            raise_error("[AMQP] remote build failed with status: {0}".format(manifest.result))

        raise_task_error_if(
            self.task.has_artifact() and not env.cache.is_available_remotely(self.task), self.task,
            "no task artifact available in any cache, check configuration")

        raise_task_error_if(
            self.task.has_artifact() and not env.cache.download(self.task) and env.cache.download_enabled(),
            self.task, "failed to download task artifact")

        for extension in self.task.extensions:
            raise_task_error_if(
                self.task.has_artifact() and not env.cache.download(extension) and env.cache.download_enabled(),
                self.task, "failed to download task artifact")

        return self.task

    @utils.retried.on_exception((ConnectionError, AMQPConnectionError, AMQPConnectorStackTimeout))
    def connect(self):
        self.connection = pika.BlockingConnection(
            parameters=pika.URLParameters(_get_url()))
        self.channel = self.connection.channel()
        if not self.callback_queue:
            self.corr_id = self.task.identity
            self.channel.exchange_declare(
                exchange=WorkerTaskConsumer.RESULT_EXCHANGE,
                exchange_type=WorkerTaskConsumer.EXCHANGE_TYPE)
            result = self.channel.queue_declare(
                '', arguments={"x-expires": 7200000})
            self.callback_queue = result.method.queue
            self.channel.queue_bind(
                self.callback_queue,
                WorkerTaskConsumer.RESULT_EXCHANGE,
                routing_key=self.corr_id)
        self.channel.basic_consume(
            queue=self.callback_queue,
            on_message_callback=self.on_response,
            auto_ack=False)
        log.debug("[AMQP] Established connection to server")

    def on_response(self, channel, basic_deliver, properties, body):
        # log.debug("[AMQP] Completion of {}, expecting {}", properties.correlation_id, self.corr_id)
        if self.corr_id == properties.correlation_id:
            self.response = body.decode()
            channel.basic_ack(basic_deliver.delivery_tag)
        else:
            channel.basic_ack(basic_deliver.delivery_tag)

    def publish_request(self, manifest, routing_key):
        props = pika.BasicProperties(
            correlation_id=self.corr_id,
            priority=self.priority,
            headers={"x-deduplication-header": self.task.identity})
        self.response = None
        self.channel.basic_publish(
            exchange=WorkerTaskConsumer.EXCHANGE,
            routing_key=routing_key,
            properties=props,
            body=manifest)

    def run(self, env):
        try:
            self.task.started(TYPE)
            hooks.task_started_execution(self.task)
            for extension in self.task.extensions:
                extension.started(TYPE)
                hooks.task_started_execution(extension)
            with hooks.task_run([self.task] + self.task.extensions):
                self._run(env)
            for extension in self.task.extensions:
                hooks.task_finished_execution(extension)
                extension.finished(TYPE)
            hooks.task_finished_execution(self.task)
            self.task.finished(TYPE)
        except (ConnectionError, AMQPConnectionError):
            log.exception()
            for extension in self.task.extensions:
                extension.failed(TYPE)
            self.task.failed(TYPE)
            raise_error("Lost connection to AMQP server")
        except Exception as e:
            log.exception()
            for extension in self.task.extensions:
                extension.failed(TYPE)
            self.task.failed(TYPE)
            raise e
        finally:
            if self.connection is not None:
                utils.call_and_catch(self.connection.close)
        return self.task


@scheduler.ExecutorFactory.Register
class AmqpExecutorFactory(scheduler.NetworkExecutorFactory):
    def __init__(self, options):
        workers = config.getint(NAME, "workers", 16)
        super(AmqpExecutorFactory, self).__init__(max_workers=workers)
        self._options = options

    @property
    def options(self):
        return self._options

    def create(self, task):
        return AmqpExecutor(self, task)


log.verbose("[AMQP] Loaded")
