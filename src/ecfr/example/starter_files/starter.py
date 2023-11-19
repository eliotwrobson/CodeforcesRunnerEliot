#!/usr/bin/env python3

import os
import sys
from io import BytesIO, IOBase

BUFSIZ = 8192


# Fast Input Classes
# From: https://codeforces.com/blog/entry/71884?#comment-926229
class FastIO(IOBase):
    newlines = 0

    def __init__(self, file):
        self._fd = file.fileno()
        self.buffer = BytesIO()
        self.writable = "n" in file.mode or "r" not in file.mode
        self.write = self.buffer.write if self.writable else None

    def read(self):
        while True:
            b = os.read(self._fd, max(os.fstat(self._fd).st_size, BUFSIZ))
            if not b:
                break
            ptr = self.buffer.tell()
            self.buffer.seek(0, 2), self.buffer.write(b), self.buffer.seek(ptr)
        self.newlines = 0
        return self.buffer.read()

    def readline(self):
        while self.newlines == 0:
            b = os.read(self._fd, max(os.fstat(self._fd).st_size, BUFSIZ))
            self.newlines = b.count(b"\n") + (not b)
            ptr = self.buffer.tell()
            self.buffer.seek(0, 2), self.buffer.write(b), self.buffer.seek(ptr)
        self.newlines -= 1
        return self.buffer.readline()

    def flush(self):
        if self.writable:
            os.write(self._fd, self.buffer.getvalue())
            self.buffer.truncate(0), self.buffer.seek(0)


class IOWrapper(IOBase):
    def __init__(self, file):
        self.buffer = FastIO(file)
        self.flush = self.buffer.flush
        self.writable = self.buffer.writable
        self.write = lambda s: self.buffer.write(s.encode("ascii"))
        self.read = lambda: self.buffer.read().decode("ascii")
        self.readline = lambda: self.buffer.readline().decode("ascii")


if sys.version_info[0] < 3:
    sys.stdin, sys.stdout = FastIO(sys.stdin), FastIO(sys.stdout)
else:
    sys.stdin, sys.stdout = IOWrapper(sys.stdin), IOWrapper(sys.stdout)
input = lambda: sys.stdin.readline().rstrip("\r\n")  # noqa: E731


# Input Functions
# From https://codeforces.com/blog/entry/71884
def inp() -> int:
    """For integer inputs"""
    return int(input())


def inlt() -> list:
    """For list inputs"""
    return list(map(int, input().split()))


def insr() -> list[str]:
    """For string inputs, as a list of characters"""
    s = input()
    return list(s[: len(s) - 1])


def invr() -> list[int]:
    """Space separated integer inputs as a list"""
    return map(int, input().split())


# Start of user code


def main() -> None:
    # Your code here!
    pass


if __name__ == "__main__":
    main()
