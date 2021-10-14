from xml.etree import ElementTree as ET


def _tcname(suite, case):
    return "{}.{}".format(suite.get("name"), case.get("name"))


def import_failures(xml, report):
    tree = ET.parse(xml)
    root = tree.getroot()
    testsuites = root.findall(".//testsuite")
    for testsuite in testsuites:
        testcases = testsuite.findall(".//testcase")
        for testcase in testcases:
            errors = testcase.findall(".//error")
            for error in errors:
                name = _tcname(testsuite, testcase)
                message = error.text
                report.add_error("Test Error", name, message)

            failures = testcase.findall(".//failure")
            for failure in failures:
                name = _tcname(testsuite, testcase)
                message = failure.text
                report.add_error("Test Failed", name, message)
