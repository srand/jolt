from xml.etree import ElementTree as ET


def _tcname(suite, case):
    return "{}.{}".format(suite.get("name"), case.get("name"))


def import_junit_report(xml, report, errors=True, failures=True):
    """
    Import errors and failures from a JUnit XML report.

    Args:
        xmlreport (str): JUnit report data to be imported (XML string).
        report: a Jolt task report, returned by ``Task.report()``
        errors (boolean): import errors from the JUnit report
        failures (boolean): import failures from the JUnit report
    """

    tree = ET.parse(xml)
    root = tree.getroot()
    testsuites = root.findall(".//testsuite")
    for testsuite in testsuites:
        testcases = testsuite.findall(".//testcase")
        for testcase in testcases:
            if errors:
                tcerrors = testcase.findall(".//error")
                for error in tcerrors:
                    name = _tcname(testsuite, testcase)
                    message = error.text
                    report.add_error("Test Error", name, message)
            if failures:
                tcfailures = testcase.findall(".//failure")
                for failure in tcfailures:
                    name = _tcname(testsuite, testcase)
                    message = failure.text
                    report.add_error("Test Failed", name, message)
