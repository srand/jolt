from copy import copy
from threading import RLock
from xml.dom import minidom

from jolt.influence import HashInfluenceProvider, HashInfluenceRegistry
from jolt.tools import Tools
from jolt import filesystem as fs
from jolt import log
from jolt.plugins import git
from jolt.scheduler import NetworkExecutorExtension, NetworkExecutorExtensionFactory
from jolt.xmldom import Attribute, Composition, SubElement, Element, ElementTree, ET


@Attribute('name')
@Attribute('fetch')
class RepoRemote(SubElement):
    def __init__(self, elem=None):
        super(RepoRemote, self).__init__('remote', elem=elem)


@Attribute('revision')
@Attribute('remote')
@Attribute('sync-j')
class RepoDefault(SubElement):
    def __init__(self, elem=None):
        super(RepoDefault, self).__init__('default', elem=elem)


@Attribute('path')
@Attribute('name')
@Attribute('revision')
@Attribute('upstream')
@Attribute('remote')
class RepoProject(SubElement):
    def __init__(self, elem=None):
        super(RepoProject, self).__init__('project', elem=elem)

    def get_diff(self):
        with self.tools.cwd(self.path_or_name):
            return self.tools.run("git diff --no-ext-diff HEAD", output_on_error=True)
        assert False, "git command failed"

    def get_head(self):
        with self.tools.cwd(self.path_or_name):
            return self.tools.run("git rev-parse HEAD", output_on_error=True).strip()
        assert False, "git command failed"

    def get_remote_branches(self, commit):
        with self.tools.cwd(self.path_or_name):
            result = self.tools.run("git branch -r --contains {0}", commit, output_on_error=True)
            if not result:
                return []
            result = result.strip().splitlines()
            result = [line.strip() for line in result]
            return result
        assert False, "git command failed"

    def get_local_commits(self):
        with self.tools.cwd(self.path_or_name):
            result = self.tools.run("git rev-list HEAD ^@{{upstream}}", output_on_error=True)
            if not result:
                return []
            result = result.strip("\r\n ")
            return result.splitlines()
        assert False, "git command failed"

    def has_local_ref(self, ref):
        with self.tools.cwd(self.path_or_name):
            try:
                return True if self.tools.run("git show-ref {0}", ref, output=False) else False
            except Exception:
                return False

    def get_remote_ref(self, commit, remote, pattern=None):
        with self.tools.cwd(self.path_or_name):
            result = self.tools.run(
                "git ls-remote {0}{1}",
                remote,
                " {0}".format(pattern) if pattern else "",
                output_on_error=True)
            if not result:
                return None
            result = result.strip().splitlines()
            result = [line.split("\t") for line in result]
            result = {line[0]: line[1] for line in result}
            return result.get(commit)
        assert False, "git command failed"

    @property
    def path_or_name(self):
        return self.path or self.name


@Composition(RepoRemote, "remote")
@Composition(RepoDefault, "default")
@Composition(RepoProject, "project")
class RepoManifest(ElementTree):
    def __init__(self, task, path):
        super(RepoManifest, self).__init__(element=Element('manifest'))
        self.path = path
        self.tools = task.tools

    def append(self, element):
        self.getroot().append(element)

    def get(self, key):
        self.getroot().get(key)

    def set(self, key, value):
        self.getroot().set(key, value)

    def parse(self, filename=".repo/manifest.xml"):
        with open(fs.path.join(self.tools.getcwd(), filename)) as f:
            root = ET.fromstring(f.read())
            self._setroot(root)
            for project in self.projects:
                project.tools = self.tools
            return self
        raise Exception("failed to parse xml file")

    def format(self):
        return minidom.parseString(ET.tostring(self.getroot())).toprettyxml(indent="  ")

    def write(self, filename):
        with open(filename, 'w') as f:
            f.write(self.format())

    def get_remote(self, project):
        if len(self.defaults) > 0:
            return project.remote or self.defaults[0].remote
        return project.remote

    def get_upstream(self, project):
        if len(self.defaults) > 0:
            return project.upstream or self.defaults[0].revision or "master"
        return project.upstream or "master"

    def assert_clean(self):
        for project in self.projects:
            assert not project.get_diff(), \
                "repo project '{0}' has local changes"\
                .format(project.path_or_name)

    def lock_revisions(self):
        for project in self.projects:
            head = project.get_head()
            if not project.get_remote_branches(head):
                remote_ref = project.get_remote_ref(
                    head, self.get_remote(project))
                assert remote_ref, \
                    "repo project '{0}' has unpublished commits"\
                    .format(project.path_or_name)
                head = remote_ref

            if not project.upstream:
                if project.revision and project.has_local_ref(project.revision):
                    project.upstream = project.revision
                else:
                    project.upstream = self.get_upstream(project)

            if not project.revision.startswith("refs/changes"):
                project.revision = head


_git_repos = {}
_git_repo_lock = RLock()

_repo_manifests = {}
_repo_manifest_lock = RLock()


class RepoInfluenceProvider(HashInfluenceProvider):
    name = "Repo"
    path = "."

    def __init__(self, path=None, include=None, exclude=None, network=True):
        self.path = path or self.__class__.path
        self.include = include
        self.exclude = exclude
        self.network = network

    def get_influence(self, task):
        self.tools = Tools(task, task.joltdir)
        try:
            manifest_path = fs.path.join(task.joltdir, task.expand(self.path))
            manifest = RepoManifest(task, manifest_path)
            manifest.parse(fs.path.join(manifest_path, ".repo", "manifest.xml"))

            result = []
            for project in sorted(manifest.projects, key=lambda p: p.name):
                if self.include is not None and project.path_or_name not in self.include:
                    continue
                if self.exclude is not None and project.path_or_name in self.exclude:
                    continue

                with _git_repo_lock:
                    gip = _git_repos.get(project.path_or_name)
                    if gip is None:
                        gip = git.GitInfluenceProvider(project.path_or_name)
                        _git_repos[project.path_or_name] = gip
                    result.append(gip.get_influence(task))

            return "\n".join(result)

        except KeyError:
            log.exception()
        assert False, "failed to calculate hash influence for repo manifest at {0}".format(self.path)

    def get_manifest(self, task):
        manifest_path = fs.path.join(task.joltdir, task.expand(self.path))
        with _repo_manifest_lock:
            manifest = _repo_manifests.get(manifest_path)
            if manifest is None:
                manifest = RepoManifest(task, manifest_path)
                manifest.parse()
                manifest.assert_clean()
                manifest.lock_revisions()
                _repo_manifests[manifest_path] = manifest
            return manifest


class RepoNetworkExecutorExtension(NetworkExecutorExtension):
    def get_parameters(self, task):
        rip = list(filter(
            lambda n: isinstance(n, RepoInfluenceProvider),
            task.task.influence))
        if rip:
            assert len(rip) == 1, "task influenced by multiple repo manifests"
            rip = rip[0]
            if rip.network:
                manifest = rip.get_manifest(task.task)
                return {"repo_manifest": manifest.format()}
        return {}


@NetworkExecutorExtensionFactory.Register
class RepoNetworkExecutorExtensionFactory(NetworkExecutorExtensionFactory):
    def create(self):
        return RepoNetworkExecutorExtension()


def global_influence(path, include=None, exclude=None, network=True, cls=RepoInfluenceProvider):
    HashInfluenceRegistry.get().register(cls(path, include, exclude, network))


def influence(path='.', include=None, exclude=None, network=True, cls=RepoInfluenceProvider):
    def _decorate(taskcls):
        if "influence" not in taskcls.__dict__:
            taskcls.influence = copy(taskcls.influence)
        provider = cls(path, include, exclude, network)
        taskcls.influence.append(provider)
        return taskcls
    return _decorate
