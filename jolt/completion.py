"""Task argument completion and persistent parameter metadata."""

import json
import os
import sqlite3
import click
import jolt_completion as standalone

from click.shell_completion import (
    BashComplete, CompletionItem, FishComplete, ZshComplete,
    add_completion_class, split_arg_string,
)

from jolt import log, utils
from jolt.influence import _ClassSourceDigests
from jolt.tasks import ListParameter, Parameter


class _TaskParameters(_ClassSourceDigests):
    """Reuse the source cache's transactions, eviction and memory fallback."""

    filename = "taskparameters.db"

    def _key(self, cls):
        return utils.hashstring("\0".join(
            base.__qualname__ + "\0" + super(_TaskParameters, self)._key(base)
            for base in cls.__mro__ if base is not object))

    @staticmethod
    def _parameters(cls):
        params = {}
        for base in reversed(cls.__mro__):
            for name in base.__dict__.get("__param_list", {}):
                param = getattr(cls, name)
                if isinstance(param, Parameter) and not param.is_const():
                    params[name] = {
                        "values": [str(value) for value in param._accepted_values or []],
                        "list": isinstance(param, ListParameter),
                    }
        return params

    def get(self, cls):
        try:
            if any(self._is_generated(base) for base in cls.__mro__ if base is not object):
                return self._parameters(cls)
            key = self._key(cls)
        except (OSError, TypeError, KeyError):
            return self._parameters(cls)
        with self._lock:
            classes = self._load(key)
            data = classes.get(cls.__qualname__)
            if data is not None:
                try:
                    return json.loads(data)
                except (ValueError, TypeError):
                    pass
            params = self._parameters(cls)
            data = json.dumps(params)
            classes[cls.__qualname__] = data
            self._new.append((key, cls.__qualname__, data))
            return params


_parameters = _TaskParameters()


def task_index(tasks):
    return {task.name: _parameters.get(task) for task in tasks}


def _index_tables(db):
    db.execute("CREATE TABLE IF NOT EXISTS workspace_indexes (path TEXT PRIMARY KEY)")
    db.execute("CREATE TABLE IF NOT EXISTS workspace_tasks ("
               "path TEXT NOT NULL, name TEXT NOT NULL, parameters TEXT NOT NULL, PRIMARY KEY (path, name))")


def _write_index(db, workspace, index):
    with db:
        _index_tables(db)
        db.execute("INSERT OR IGNORE INTO workspace_indexes (path) VALUES (?)", (workspace,))
        db.execute("DELETE FROM workspace_tasks WHERE path = ?", (workspace,))
        db.executemany("INSERT INTO workspace_tasks (path, name, parameters) VALUES (?, ?, ?)",
                       [(workspace, name, json.dumps(params)) for name, params in index.items()])
        if db.execute("SELECT 1 FROM sqlite_master WHERE name = 'workspaces'").fetchone():
            db.execute("DELETE FROM workspaces WHERE path = ?", (workspace,))


def read_index(workspace, incomplete=""):
    db = _parameters._connect()
    if db is None:
        return None
    workspace = os.path.realpath(workspace)
    try:
        _index_tables(db)
        if not db.execute("SELECT 1 FROM workspace_indexes WHERE path = ?", (workspace,)).fetchone():
            # Migrate old whole-workspace indexes without executing recipes.
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'workspaces'").fetchone():
                return None
            row = db.execute("SELECT tasks FROM workspaces WHERE path = ?", (workspace,)).fetchone()
            if row is None:
                return None
            _write_index(db, workspace, json.loads(row[0]))
        return standalone.read_tasks(db, workspace, incomplete)
    except (sqlite3.Error, ValueError, TypeError):
        return None


def command_metadata(command):
    def parameter(param):
        data = {"nargs": param.nargs, "hidden": getattr(param, "hidden", False)}
        if isinstance(param.type, click.Choice):
            data["choices"] = [str(value) for value in param.type.choices]
        elif isinstance(param.type, click.Path):
            data["kind"] = "dir" if not param.type.file_okay else "file"
        elif isinstance(param.type, click.File):
            data["kind"] = "file"
        if isinstance(param, click.Option) and (param.is_flag or param.count):
            data["nargs"] = 0
        if isinstance(param, click.Option) and "--chdir" in param.opts:
            data["kind"] = "dir"
        elif isinstance(param, click.Option) and "--config" in param.opts:
            data["kind"] = "file"
        if isinstance(param, click.Argument):
            callback = getattr(param, "_custom_shell_complete", None)
            data["task"] = getattr(callback, "__name__", None) == "_autocomplete_tasks"
        return data

    metadata = {"options": {}, "arguments": [], "commands": {}}
    for param in command.params:
        data = parameter(param)
        if isinstance(param, click.Option):
            for name in param.opts + param.secondary_opts:
                metadata["options"][name] = data
        else:
            metadata["arguments"].append(data)
    metadata["options"].setdefault("--help", {"nargs": 0, "hidden": False})
    if isinstance(command, click.Group):
        metadata["commands"] = {name: command_metadata(child) for name, child in command.commands.items()
                                if not child.hidden}
    return metadata


def update_commands(command):
    db = _parameters._connect()
    if db is None:
        return
    try:
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS completion_commands (id INTEGER PRIMARY KEY, metadata TEXT NOT NULL)")
            db.execute("INSERT OR REPLACE INTO completion_commands VALUES (1, ?)",
                       (json.dumps(command_metadata(command)),))
    except sqlite3.Error as e:
        log.debug("Failed to save command completion index: {}", e)


def update_index(workspace, tasks):
    index = task_index(tasks)
    db = _parameters._connect()
    if db is not None:
        try:
            _write_index(db, os.path.realpath(workspace), index)
        except sqlite3.Error as e:
            log.debug("Failed to save completion index: {}", e)
    return index


def _item(value, unfinished=True):
    return CompletionItem(value, type="jolt_nospace" if unfinished else "plain")


def complete_tasks(tasks, incomplete):
    if not isinstance(tasks, dict):
        tasks = task_index(tasks)
    return [CompletionItem(item.value, type=item.type)
            for item in standalone.complete_tasks(tasks, incomplete)]


@add_completion_class
class JoltBashComplete(BashComplete):
    source_template = BashComplete.source_template.replace(
        'COMP_WORDS="${COMP_WORDS[*]}"',
        'JOLT_COMPLETE_LINE="${COMP_LINE:0:COMP_POINT}" COMP_WORDS="${COMP_WORDS[*]}"',
    ).replace(
        "    local response\n", "    local response\n    compopt +o nospace\n",
    ).replace(
        "elif [[ $type == 'plain' ]]; then",
        "elif [[ $type == 'jolt_nospace' ]]; then\n"
        "            compopt -o nospace\n"
        "            COMPREPLY+=(\"$value\")\n"
        "        elif [[ $type == 'plain' ]]; then",
    )

    def get_completion_args(self):
        line = os.environ.get("JOLT_COMPLETE_LINE")
        if line is None:
            return super().get_completion_args()
        words = split_arg_string(line)
        if line.endswith(" "):
            return words[1:], ""
        return words[1:-1], words[-1] if words else ""

    def format_completion(self, item):
        # Readline replaces only the suffix after a word-break character.
        _, incomplete = self.get_completion_args()
        value = item.value
        boundary = max(incomplete.rfind(":"), incomplete.rfind("=")) + 1
        prefix = incomplete[:boundary]
        if value.startswith(prefix):
            value = value[boundary:]
        return f"{item.type},{value}"


@add_completion_class
class JoltZshComplete(ZshComplete):
    source_template = ZshComplete.source_template.replace(
        'if [[ "$type" == "plain" ]]; then',
        'if [[ "$type" == "jolt_nospace" ]]; then\n'
        '            compadd -U -V unsorted -S \'\' -- "$key"\n'
        '        elif [[ "$type" == "plain" ]]; then',
    )


@add_completion_class
class JoltFishComplete(FishComplete):
    source_template = FishComplete.source_template.replace(
        'set -l metadata (string split "," $completion);',
        'set -l metadata (string split -m 1 "," $completion);',
    ).replace(
        'else if test $metadata[1] = "plain";',
        'else if test $metadata[1] = "plain"; or test $metadata[1] = "jolt_nospace";',
    )
