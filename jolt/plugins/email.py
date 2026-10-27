from contextlib import contextmanager
import copy
import smtplib
from email.message import EmailMessage
import os
from jolt import config
from jolt import filesystem as fs
from jolt import log
from jolt import utils
from jolt.error import raise_error_if
from jolt.plugins import report
from jolt.hooks import CliHook, CliHookFactory
from jolt.tasks import TaskRegistry


class EmailHooks(CliHook):
    def __init__(self):
        self._server = config.get("email", "server")
        self._to = config.get("email", "to")
        self._cc = config.get("email", "cc")
        self._bcc = config.get("email", "bcc")
        self._from = config.get("email", "from", "jolt@localhost")
        self._subject = config.get("email", "subject", "Jolt Build Report")
        self._template = config.get(
            "email", "template",
            fs.path.join(fs.path.dirname(__file__), "..", "templates", "email.html.template"))
        self._artifact = config.get("email", "artifact")
        self._failure = config.getboolean("email", "on_failure", True)
        self._success = config.getboolean("email", "on_success", True)
        raise_error_if(not self._server, "email.server not configured")
        raise_error_if(not self._server, "email.to not configured")
        raise_error_if(
            config.get("email", "stylesheet"),
            "email.stylesheet is no longer supported, use email.template with a Jinja template")

    def render_report(self, report):
        from jinja2 import Environment, FileSystemLoader
        env = Environment(
            loader=FileSystemLoader(fs.path.dirname(self._template)),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True)
        template = env.get_template(fs.path.basename(self._template))
        return template.render(report=report, environ=os.environ)

    def shorten_task_names(self, report):
        # Use the short qualified task names in the report
        for mtask in report.tasks:
            with utils.ignore_exception():
                # mtask.name is a fully qualified name
                task = TaskRegistry.get().get_task(mtask.name)
                mtask.name = task.short_qualified_name

    def send_report(self, report):
        self.shorten_task_names(report)
        html = self.render_report(report)

        if self._artifact:
            dirname = fs.path.dirname(self._artifact)
            if dirname:
                fs.makedirs(dirname)
            with open(self._artifact, "w") as f:
                f.write(html)

        if report.has_failure() or report.has_unstable():
            if not self._failure:
                return
        else:
            if not self._success or not report.has_tasks():
                return

        msg = EmailMessage()
        msg['Subject'] = self._subject
        msg['From'] = self._from
        msg['To'] = ", ".join(utils.unique_list(self._to.split()))
        if self._cc:
            msg['Cc'] = ", ".join(utils.unique_list(self._cc.split()))
        if self._bcc:
            msg['Bcc'] = ", ".join(utils.unique_list(self._bcc.split()))
        msg.set_content("Your e-mail client cannot display HTML formatted e-mails.")
        msg.add_alternative(html, subtype='html')

        with smtplib.SMTP(self._server) as server:
            log.info("Sending email report to {}", self._to)
            server.send_message(msg)

    @contextmanager
    def cli_build(self, *args, **kwargs):
        start = utils.duration()
        try:
            yield
        finally:
            with report.update() as manifest:
                manifest = copy.copy(manifest)
                manifest.duration = str(int(start.seconds))
                self.send_report(manifest)


@CliHookFactory.register
class ResultFactory(CliHookFactory):
    def create(self, env):
        return EmailHooks()
