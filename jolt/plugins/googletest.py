from xml.etree import ElementTree as ET

def import_failures(xml, report):
    tree = ET.parse(xml)
    root = tree.getroot()
    testsuites = root.findall(".//testsuite")
    for testsuite in testsuites:
        testcases = testsuite.findall(".//testcase")
        for testcase in testcases:
            failures = testcase.findall(".//failure")
            for failure in failures:
                tsname = testsuite.get("name")
                tcname = testcase.get("name")
                name = tsname + "." + tcname
                message = failure.text
                report.add_error("Test Failed", name, message)
