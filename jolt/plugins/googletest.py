from jolt.plugins import junit
from jolt.utils import deprecated


@deprecated
def import_failures(xml, report):
    return junit.import_junit_report(xml, report, errors=True, failures=True)
