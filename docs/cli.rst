Command Line
============

Previewing rebuilds
-------------------

Use ``--dry-prepare`` and ``--dry-run`` to see which tasks are affected by a
change before building them. First, save a workspace-wide baseline of task hashes::

    jolt build --dry-prepare mytask

Then edit a source file and compare the updated workspace against the
saved baseline::

    jolt build --dry-run mytask

Jolt prints a ``Would build:`` line with the task name, current hash and rebuild
reason for each new or changed task, followed by a total. The reason identifies
each direct dependency whose hash changed, or which was added or removed. For
example, changing a source file used by ``source`` can produce::

    Would build: source (<hash>) - task inputs or definition changed
    Would build: consumer (<hash>) - dependency 'source' changed
    Would build: package (<hash>) - dependency 'consumer' changed
    Dry run: 3 tasks would be built

This shows the dependency chain responsible for the rebuild. A task with no
baseline is marked ``new task (no baseline)``. If its dependencies are unchanged,
the reason is ``task inputs or definition changed``; exact source files or other
task-local inputs are not distinguished. Aliases and resources can be named as
dependency causes even though they are not themselves listed as build tasks.
Requirements expanded through an alias are also reported when they directly
influence the consumer's hash. Dependency names include parameter values to
distinguish task variants.
Changes to a task's hash propagate to
all its direct and transitive consumers, including packages outside the
command-line target's dependency tree, so they are listed too. Files must be
declared as hash influences by the recipe, for example with
``@influence.files("src/**")``. Parameter changes can also be previewed::

    jolt build --dry-prepare mytask:mode=debug
    jolt build --dry-run mytask:mode=release

Both options calculate task hashes without executing build tasks or acquiring
regular task resources. Workspace resources needed to load recipes and
calculate hashes are prepared as usual. Both commands include all registered
tasks with usable default parameters, plus variants declared in requirements or
passed on the command line. Tasks with unset required parameters are included
when their parameters are supplied by a requirement, the command line, or
``--default``. Arbitrary parameter combinations are not enumerated.
Automatically discovered default tasks are included only when their complete
dependency trees can be resolved. Unconfigured template defaults, including
decorator wrappers, and defaults with invalid dependencies are skipped with a
verbose message identifying the task and error, including unresolved macros,
failures in dynamic requirement calculations, unsupported dependency parameters,
or dependency cycles. Configured variants reached through valid requirements
are still included. Errors in an explicitly requested target or its dependencies
remain errors.
If an automatically discovered task's hash cannot be calculated, that task and
all of its consumers are excluded from the baseline
and preview. Independent tasks and valid configured variants are still compared.
Use ``-v`` to see diagnostics for skipped default configurations. These values
are resolved during task construction and hash calculation, as in a normal build,
without executing ``Task.run()``.
The comparison covers the workspace regardless of whether artifacts are already
cached. Unchanged tasks and non-buildable aliases and resources are omitted from
the preview.

The temporary SQLite database is stored as ``dry-run.db`` in the workspace's
build directory (``build/dry-run.db`` by default). Each ``--dry-prepare`` replaces
the baseline with the workspace tasks, requested variants and their direct
dependency links. ``--dry-run``
keeps it unchanged, so you can compare several edits against the same baseline.
Removing the build directory removes the baseline; prepare it again before the
next dry run. Multiple targets can be passed to either command. The two options
are mutually exclusive and cannot be combined with ``--force``.
Baselines prepared by older versions still support hash comparison and reporting
changed dependencies. Run ``--dry-prepare`` again to also identify added or removed
dependencies.

Shell completion
----------------

Enable fast Bash completion with the standalone helper::

    eval "$(jolt-completion --bash-source)"

When running from a source checkout without installing Jolt, use::

    eval "$(python3 /path/to/jolt/jolt_completion.py --bash-source)"

Shell initialization (``--bash-source``) imports Jolt once to refresh command
and option metadata, including configured plugins, without loading recipes or
updating tasks. Each subsequent completion request uses only the Python standard
library and reads the index without importing Jolt or Click. It supports commands,
options, choice values, file paths, and task parameters. Run ``jolt list`` once to
populate the task index. If the task index is missing, task completion returns no
suggestions; completion requests never start Jolt or execute recipes. Global ``-c``/``--config`` and
``-C``/``--chdir`` options select the cache and workspace used for completion.

Click's integration remains available for Zsh and Fish (``zsh_source`` and
``fish_source``), and as a Bash fallback (``bash_source``)::

    eval "$(_JOLT_COMPLETE=bash_source jolt)"

Regenerate previously installed completion scripts to enable parameter completion.

Completion first fills in the task name. Complete again to select an unused
parameter (``task:parameter=``), then select a predefined value when available.
After a value, completion offers the remaining parameters with a comma separator.
Parameters without predefined values accept manually entered values. Constant
parameters are not offered, and list parameters also offer additional values
separated by ``+``.

Completion reads a persistent index for the current workspace without loading
recipes. Indexed queries fetch only task names matching the current prefix, or
only the exact task when completing its parameters. If no index exists, recipes are loaded once to create it. Normal recipe
loads (for example, ``jolt list`` or ``jolt build``) refresh the index, so run one
of those commands after adding, removing or changing tasks to update completion.
An existing empty index is also used without loading recipes.

The workspace index and parameter metadata are stored in ``taskparameters.db``
in the Jolt cache directory. During normal loads, unchanged task classes reuse
cached parameter names and values, keyed by the task and base-class module
contents and Python version. Generated classes are inspected on each normal load.
If the database is unavailable, completion falls back to loading recipes.

.. reference-cli-start

.. _reference-cli-build:
.. click:: cli:build
	   :prog: jolt build
.. _reference-cli-clean:
.. click:: cli:clean
	   :prog: jolt clean
.. _reference-cli-config:
.. click:: cli:_config
	   :prog: jolt config
.. _reference-cli-display:
.. click:: cli:display
	   :prog: jolt display
.. _reference-cli-docs:
.. click:: cli:docs
	   :prog: jolt docs
.. _reference-cli-export:
.. click:: cli:export
	   :prog: jolt export
.. _reference-cli-inspect:
.. click:: cli:inspect
	   :prog: jolt inspect
.. _reference-cli-list:
.. click:: cli:_list
	   :prog: jolt list
.. _reference-cli-log:
.. click:: cli:_log
	   :prog: jolt log
.. _reference-cli-login:
.. click:: cli:_login
	   :prog: jolt login
.. _reference-cli-token:
.. click:: cli:_token
	   :prog: jolt token
.. _reference-cli-logout:
.. click:: cli:_logout
	   :prog: jolt logout
.. _reference-cli-report:
.. click:: cli:_report
	   :prog: jolt report

.. reference-cli-end
