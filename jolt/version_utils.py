import operator
import re


class version(object):
    def __init__(self, verstr):
        if type(verstr) is str:
            match = re.search(r"(?P<major>[\d]+)\.(?P<minor>[\d]+)(\.(?P<patch>[\d]+))?", verstr)
            if not match:
                raise ValueError(verstr)
            values = match.groupdict()
            self.major = int(values["major"])
            self.minor = int(values["minor"])
            self.patch = int(values["patch"]) if values["patch"] else None
        elif type(verstr) is tuple:
            if len(verstr) < 2 or len(verstr) > 3:
                raise ValueError(verstr)
            self.major = verstr[0]
            self.minor = verstr[1]
            self.patch = verstr[2] if len(verstr) == 3 else None
        else:
            raise ValueError(verstr)

    def __str__(self):
        if self.patch is None:
            return f"{self.major}.{self.minor}"
        else:
            return f"{self.major}.{self.minor}.{self.patch}"

    def __repr__(self):
        return str(self)

    def __eq__(self, version):
        if self.major != version.major:
            return False
        if self.minor != version.minor:
            return False
        if self.patch is None or version.patch is None:
            return True
        if self.patch != version.patch:
            return False
        return True

    def __lt__(self, version):
        if self.major < version.major:
            return True
        if self.major > version.major:
            return False
        if self.minor < version.minor:
            return True
        if self.minor > version.minor:
            return False
        if self.patch is None or version.patch is None:
            return False
        if self.patch < version.patch:
            return True
        return False

    def __le__(self, version):
        return self < version or self == version

    def __gt__(self, version):
        if self.major > version.major:
            return True
        if self.major < version.major:
            return False
        if self.minor > version.minor:
            return True
        if self.minor < version.minor:
            return False
        if self.patch is None or version.patch is None:
            return False
        if self.patch > version.patch:
            return True
        return False

    def __ge__(self, version):
        return self > version or self == version


class version_operator(object):
    def __init__(self, verstr):
        match = re.search(r"(?P<operator>((>|<)?=|>))?", verstr)
        if not match:
            raise ValueError(verstr)
        self.opstr = match.groupdict("=")["operator"]
        if self.opstr == "=":
            self.op = operator.eq
        elif self.opstr == ">":
            self.op = operator.gt
        elif self.opstr == ">=":
            self.op = operator.ge
        elif self.opstr == "<=":
            self.op = operator.le
        else:
            ValueError(self.opstr)

    def __call__(self, a, b):
        return self.op(a, b)

    def __repr__(self):
        return repr(self.opstr)

    def __str__(self):
        return str(self.opstr)


class requirement(object):
    def __init__(self, verstr):
        self.operator = version_operator(verstr)
        self.version = version(verstr)

    def satisfied(self, version):
        """ Returns True if the version satisfies the requirement """
        return self.operator(version, self.version)

    def required(self):
        """ Returns the least required version """
        if self.operator.opstr == ">":
            if self.version.patch is None:
                return version((self.version.major, self.version.minor + 1))
            return version((self.version.major, self.version.minor, self.version.patch + 1))
        else:
            return self.version

    def __str__(self):
        return f"{self.operator}{self.version}"
