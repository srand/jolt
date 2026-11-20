"""Standalone, standard-library-only Bash completion for Jolt."""

import configparser
from contextlib import closing
import glob
import json
import os
import shlex
import sqlite3
import sys
from collections import namedtuple
from urllib.parse import quote


Item = namedtuple("Item", "value type")


def _item(value, unfinished=True):
    return Item(value, "jolt_nospace" if unfinished else "plain")


def read_tasks(db, workspace, incomplete=""):
    name, separator, _ = (incomplete or "").partition(":")
    query = "SELECT name, parameters FROM workspace_tasks WHERE path = ?"
    args = [os.path.realpath(workspace)]
    if separator:
        query += " AND name = ?"
        args.append(name)
    elif name:
        query += " AND name >= ?"
        args.append(name)
        upper = name.rstrip("\U0010ffff")
        if upper:
            query += " AND name < ?"
            args.append(upper[:-1] + chr(ord(upper[-1]) + 1))
    return {name: json.loads(params) for name, params in db.execute(query, args)}


def complete_tasks(tasks, incomplete):
    incomplete = incomplete or ""
    name, sep, arguments = incomplete.partition(":")
    if not sep:
        matches = {key: params for key, params in tasks.items() if key.startswith(name)}
        if name not in matches:
            return [_item(key, bool(params)) for key, params in sorted(matches.items())]
        return [_item(name + ":" + param + "=") for param in sorted(matches[name])]
    params = tasks.get(name)
    if params is None:
        return []
    parts = arguments.split(",")
    used = {part.partition("=")[0] for part in parts[:-1]}
    current = parts[-1]
    prefix = name + ":" + ",".join(parts[:-1])
    if len(parts) > 1:
        prefix += ","
    param, equal, value = current.partition("=")
    remaining = sorted(set(params) - used)
    if not equal:
        return [_item(prefix + key + "=") for key in remaining if key.startswith(param)]
    if param not in remaining:
        return []
    metadata = params[param]
    values = metadata["values"]
    value_prefix = ""
    selected = []
    if metadata["list"] and "+" in value:
        selected = value.split("+")[:-1]
        value_prefix = "+".join(selected) + "+"
        value = value.split("+")[-1]
    matches = [candidate for candidate in values if candidate.startswith(value) and candidate not in selected]
    if values and value not in values:
        return [_item(prefix + param + "=" + value_prefix + candidate,
                      len(remaining) > 1 or metadata["list"]) for candidate in sorted(matches)]
    if not value:
        return []
    result = [_item(incomplete + "," + key + "=") for key in remaining if key != param]
    if metadata["list"]:
        result += [_item(incomplete + "+" + candidate) for candidate in sorted(values)
                   if candidate not in selected and candidate != value]
    return result


def bash_completions(items, incomplete, comp_type=""):
    """Return (type, value) pairs relative to the word that Readline completes."""
    # Readline replaces only the suffix after the last word-break character.
    boundary = max(incomplete.rfind(":"), incomplete.rfind("=")) + 1
    prefix, word = incomplete[:boundary], incomplete[boundary:]
    result = [(item.type, item.value[boundary:] if item.value.startswith(prefix) else item.value)
              for item in items]
    # Readline lists matches as given, including parameters and values before
    # the last "," or "+". When the matches don't extend the word, list them
    # without that part on a repeated Tab (63) and with show-all-if-ambiguous
    # (33): Readline then inserts their common prefix only if it is at least as
    # long as the word. With show-all-if-unmodified (64), it lists nothing if
    # they have a common prefix.
    separator = max(word.rfind(","), word.rfind("+")) + 1
    values = [value for _, value in result]
    if separator and len(values) > 1 and os.path.commonprefix(values) == word and \
            (comp_type in ("63", "33") or (comp_type == "64" and separator == len(word))):
        result = [(kind, value[separator:]) for kind, value in result]
    return result


def split_line(line):
    lexer = shlex.shlex(line, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    words = []
    try:
        while True:
            word = lexer.get_token()
            if word is None:
                break
            words.append(word)
    except ValueError:
        words.append(lexer.token)
    if not words or (line[-1:].isspace() and lexer.state not in ("'", '"')):
        words.append("")
    return words


def settings(words):
    cwd = os.getcwd()
    configs = []
    index = 0
    while index < len(words):
        word = words[index]
        if word in ("-C", "--chdir", "-c", "--config"):
            index += 1
            if index == len(words):
                break
            value = words[index]
        elif word.startswith(("--chdir=", "--config=")):
            word, value = word.split("=", 1)
        elif word.startswith(("-C", "-c")) and len(word) > 2:
            word, value = word[:2], word[2:]
        elif not word.startswith("-"):
            break
        else:
            if word in ("--interpreter", "-s", "--salt", "-j", "--jobs"):
                index += 1
            index += 1
            continue
        if word in ("-C", "--chdir"):
            cwd = os.path.abspath(value)
        else:
            configs.append(value)
        index += 1
    home = os.path.expanduser("~")
    directory = os.environ.get("JOLT_CONFIG_PATH", os.path.join(home, ".config", "jolt"))
    parser = configparser.ConfigParser()
    parser.read([os.path.join(directory, "config"), os.path.join(directory, "user")])
    overlay = os.environ.get("JOLT_CONFIG_OVERLAY")
    if overlay:
        parser.read([os.path.join(directory, overlay) if os.environ.get("JOLT_CONFIG_PATH") else overlay])
    for value in configs:
        path = os.path.abspath(value)
        if os.path.isfile(path):
            parser.read(path)
        elif value.startswith("jolt.cachedir="):
            if not parser.has_section("jolt"):
                parser.add_section("jolt")
            parser.set("jolt", "cachedir", value.partition("=")[2])
    cachedir = parser.get("jolt", "cachedir", fallback=os.path.join(home, ".cache", "jolt"))
    cachedir = cachedir.replace("{userhome}", home)
    return cwd, os.path.abspath(os.path.join(cwd, cachedir))


def value_completions(option, incomplete):
    kind = option.get("kind")
    if kind in ("file", "dir"):
        return [Item(incomplete, kind)]
    return [Item(value, "plain") for value in option.get("choices", []) if value.startswith(incomplete)]


def resolve_command(metadata, words):
    command = metadata
    position = 0
    positional = []
    options_enabled = True
    while position < len(words):
        word = words[position]
        options = command["options"]
        if options_enabled and word == "--":
            options_enabled = False
        elif options_enabled and word.startswith("-"):
            name, equals, value = word.partition("=")
            option = options.get(name)
            if option is None and not word.startswith("--"):
                for offset, char in enumerate(word[1:], 1):
                    option = options.get("-" + char)
                    if option and option["nargs"]:
                        equals = offset < len(word) - 1
                        break
            if option and option["nargs"] and not equals:
                count = option["nargs"]
                if position + count >= len(words):
                    return command, positional, option, options_enabled
                position += count
        elif not positional and word in command.get("commands", {}):
            command = command["commands"][word]
            options_enabled = True
        else:
            positional.append(word)
        position += 1
    return command, positional, None, options_enabled


def find_workspace(db, cwd):
    workspace = os.path.realpath(cwd)
    while True:
        if glob.glob(os.path.join(workspace, "*.jolt")) or db.execute(
                "SELECT 1 FROM workspace_indexes WHERE path = ?", (workspace,)).fetchone():
            return workspace
        parent = os.path.dirname(workspace)
        if parent == workspace:
            return None
        workspace = parent


def complete_line(line):
    words = split_line(line)[1:]
    if not words:
        words = [""]
    incomplete = words[-1]
    cwd, cachedir = settings(words[:-1])
    path = os.path.join(cachedir, "taskparameters.db")
    if not os.path.isfile(path):
        return []
    try:
        with closing(sqlite3.connect("file:" + quote(path) + "?mode=ro", uri=True, timeout=0.05)) as db:
            row = db.execute("SELECT metadata FROM completion_commands WHERE id = 1").fetchone()
            if row is None:
                return []
            def values(param, incomplete):
                if not param.get("task"):
                    return value_completions(param, incomplete)
                workspace = find_workspace(db, cwd)
                if workspace is None:
                    return []
                return complete_tasks(read_tasks(db, workspace, incomplete), incomplete)

            command, positional, pending, options_enabled = resolve_command(json.loads(row[0]), words[:-1])
            if pending:
                return values(pending, incomplete)
            if options_enabled and incomplete.startswith("-"):
                name, equals, value = incomplete.partition("=")
                if equals and name in command["options"]:
                    return [Item(name + "=" + item.value, item.type)
                            for item in values(command["options"][name], value)]
                return [Item(name, "plain") for name, option in sorted(command["options"].items())
                        if not option["hidden"] and name.startswith(incomplete)]
            commands = command.get("commands", {})
            if commands:
                return [Item(name, "plain") for name in sorted(commands) if name.startswith(incomplete)]
            arguments = command["arguments"]
            offset = len(positional)
            argument = None
            for candidate in arguments:
                if candidate["nargs"] == -1 or offset < candidate["nargs"]:
                    argument = candidate
                    break
                offset -= candidate["nargs"]
            if not argument:
                return []
            return values(argument, incomplete)
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, configparser.Error):
        return []


BASH_SOURCE = '''_jolt_standalone_complete() {
    local response type value
    COMPREPLY=()
    compopt +o nospace
    response=$(JOLT_COMPLETE_LINE="${COMP_LINE:0:COMP_POINT}" JOLT_COMPLETE_TYPE="$COMP_TYPE" %(helper)s)
    while IFS=, read -r type value; do
        case "$type" in
            jolt_nospace) compopt -o nospace; COMPREPLY+=("$value") ;;
            plain) COMPREPLY+=("$value") ;;
            file) compopt -o default ;;
            dir) compopt -o dirnames; mapfile -t COMPREPLY < <(compgen -d -- "$value") ;;
        esac
    done <<< "$response"
}
complete -o nosort -F _jolt_standalone_complete jolt
'''


def refresh_commands():
    # Only shell initialization imports Jolt; each Tab request stays stdlib-only.
    from contextlib import redirect_stdout
    with redirect_stdout(sys.stderr):
        from jolt.cli import cli
        from jolt.completion import update_commands
        from jolt.loader import JoltLoader
        JoltLoader.get().load_plugins()
        update_commands(cli)


def main():
    if sys.argv[1:] == ["--bash-source"]:
        refresh_commands()
        helper = shlex.quote(sys.executable) + " -S " + shlex.quote(os.path.abspath(__file__))
        print(BASH_SOURCE % {"helper": helper})
        return
    line = os.environ.get("JOLT_COMPLETE_LINE", "")
    try:
        items = complete_line(line)
    except (OSError, ValueError, configparser.Error):
        items = []
    incomplete = split_line(line)[-1]
    for kind, value in bash_completions(items, incomplete, os.environ.get("JOLT_COMPLETE_TYPE", "")):
        if "\n" not in value and "\r" not in value:
            print(f"{kind},{value}")


if __name__ == "__main__":
    main()
