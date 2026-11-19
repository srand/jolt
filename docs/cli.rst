Command Line
============

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
