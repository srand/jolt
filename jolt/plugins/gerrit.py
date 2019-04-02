from jolt import Parameter, Export
from jolt.tasks import TaskRegistry
from jolt.plugins import git


class GerritSrc(git.GitSrc):
    name = "gerrit-src"
    url = Parameter(help="URL to the Gerrit git repo to be cloned. Required.")
    sha = Parameter(required=False, help="Specific commit or tag to be checked out. Optional.")
    path = Parameter(required=False, help="Local path where the repository should be cloned.")
    _revision = Export(value=lambda self: self._get_revision() or self.git.head())

    def __init__(self, *args, **kwargs):
        refspec1 = '+refs/heads/*:refs/remotes/gerrit/*'
        refspec2 = '+refs/changes/*:refs/remotes/gerrit/changes/*'
        super(GerritSrc, self).__init__(*args, refspecs=[refspec1, refspec2], **kwargs)


class Gerrit(git.Git):
    name = "gerrit"
    url = Parameter(help="URL to the Gerrit git repo to be cloned. Required.")
    sha = Parameter(required=False, help="Specific commit or tag to be checked out. Optional.")
    path = Parameter(required=False, help="Local path where the repository should be cloned.")
    _revision = Export(value=lambda self: self._get_revision() or self.git.head())

    def __init__(self, *args, **kwargs):
        refspec1 = '+refs/heads/*:refs/remotes/gerrit/*'
        refspec2 = '+refs/changes/*:refs/remotes/gerrit/changes/*'
        super(Gerrit, self).__init__(*args, refspecs=[refspec1, refspec2], **kwargs)


TaskRegistry.get().add_task_class(GerritSrc)
TaskRegistry.get().add_task_class(Gerrit)