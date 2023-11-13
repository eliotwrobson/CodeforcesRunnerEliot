#! /usr/bin/env python2
# -*- coding: utf-8 -*-

import itertools as it
import json
import math
import os.path
import re
import subprocess
import sys
import time
import urllib.request as ulr
from optparse import OptionParser

import lxml.html as lh
import requests
from bs4 import BeautifulSoup
from lxml import etree

CODEFORCES_URL = "http://codeforces.com"


class Executer(object):
    def __init__(self, env, id) -> None:
        self.env = env
        self.id = id

    def compile(self):
        if len(self.env["compile"]) == 0:
            return 0
        return subprocess.call(self.env["compile"].format(self.id), shell=True)

    def execute(self, input_str: str) -> tuple[str, int, float]:
        proc = subprocess.Popen(
            self.env["execute"].format(self.id),
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        start = time.perf_counter()
        (stdout_data, stderr_data) = proc.communicate(bytes(input_str, "utf-8"))
        proc.wait()
        end = time.perf_counter()
        return (stdout_data.decode(), proc.returncode, end - start)


def add_options():
    usage = "%prog [options] [source code]"
    parser = OptionParser(usage=usage)
    parser.add_option(
        "-c",
        "--contest",
        dest="contest_id",
        help="Download the specific contest. \
                              If the PROBLEM_ID isn't specified, \
                              then download all problems in the contest.",
    )
    parser.add_option(
        "-p",
        "--problem",
        dest="problem_id",
        help="Download the specific problem. \
                              The CONTEST_ID is required.",
    )
    return parser.parse_args()


def install_proxy():
    if hasattr(conf, "HTTP_PROXY"):
        proxy = ulr.ProxyHandler({"http": conf.HTTP_PROXY})
        opener = ulr.build_opener(proxy)
        ulr.install_opener(opener)


def download_contest(contest_id: str) -> None:
    contest_url = "/".join((CODEFORCES_URL, "contest", contest_id))
    contest_page = ulr.urlopen(contest_url)
    tree = lh.document_fromstring(contest_page.read())
    for i in tree.xpath(
        ".//table[contains(@class, 'problems')]" "//td[contains(@class, 'id')]/a"
    ):
        download_problem(contest_id, i.text.strip())


def download_problem(contest_id: str, problem_id: str) -> None:
    problem_url = "/".join(
        (CODEFORCES_URL, "contest", contest_id, "problem", problem_id)
    )

    req = requests.get(problem_url, headers={"User-Agent": "Mozilla/5.0"})

    parser = BeautifulSoup(req.text, "lxml")

    title = parser.find_all("div", {"class": "title"})
    name = title[0].text[3:]

    filename = conf["PATTERN"].format(id=problem_id, name=name, contest=contest_id)
    filename = re.sub(r"upper\((.*?)\)", lambda x: x.group(1).upper(), filename)
    filename = re.sub(r"lower\((.*?)\)", lambda x: x.group(1).lower(), filename)
    filename = filename.replace(" ", conf["REPLACE_SPACE"])
    filename += conf["EXTENSION"]

    with open(filename, "w") as f:
        for input_node, answer_node in zip(
            parser.find_all("div", {"class": "input"}),
            parser.find_all("div", {"class": "output"}),
        ):
            input_field = input_node.find_all("pre")[0].text
            answer_field = answer_node.find_all("pre")[0].text
            # TODO replace with better library.
            f.write("<input>\n")
            f.write(input_field.replace("<br/>", "\n"))
            f.write("\n")
            f.write("</input>\n")
            f.write("<answer>\n")
            f.write(answer_field.replace("<br/>", "\n"))
            f.write("\n")
            f.write("</answer>\n")

    print(
        "contest={0!r}, id={1!r}, problem={2!r} is downloaded.".format(
            contest_id, problem_id, name
        )
    )


def is_integer(s: str) -> bool:
    try:
        int(s)
    except ValueError:
        return False
    return True


def is_number(s: str) -> bool:
    try:
        float(s)
    except ValueError:
        return False
    return True


# TODO replace with difflib
def check_result(answer_text: str, output_text: str) -> bool:
    answer_tokens = answer_text.split()
    output_tokens = output_text.split()
    if len(answer_tokens) != len(output_tokens):
        return False
    for answer_token, output_token in zip(answer_tokens, output_tokens):
        if is_integer(answer_token) and is_integer(output_token):
            if int(answer_token) != int(output_token):
                return False
        elif is_number(answer_token) and is_number(output_token):
            if not math.isclose(
                float(answer_token), float(output_token), abs_tol=10 ** (-6)
            ):
                return False
        else:
            if answer_token != output_token:
                return False
    return True


def print_center_separated(target_str: str, width: int = 100) -> None:
    rem_width = (width - len(target_str)) // 2
    side_thing = "=" * (rem_width - 1)
    res = side_thing + " " + target_str + " " + side_thing
    print(res)


def handle_test(executer: Executer, case, input_text: str, answer_text: str):
    output_text, return_code, time_taken = executer.execute(input_text)
    print_center_separated("Output")
    print(output_text)
    if return_code != 0:
        result = "RE"
    elif answer_text == output_text:
        result = "EXACTLY"
    elif check_result(answer_text, output_text):
        result = "AC"
    else:
        result = "WA"

    if result != "EXACTLY":
        print_center_separated("Answer")
        print(answer_text)

    print_center_separated(f" Case #{case}: {result} ({time_taken*1000:0.2f} ms) ")
    if result != "EXACTLY":
        # TODO was raw input
        input("press enter to continue or <C-c> to leave.")


def main() -> None:
    global options, conf
    (options, args) = add_options()

    try:
        with open("conf.json", "r") as f:
            conf = json.load(f)
    except ImportError:
        print("conf.py does not exist.")
        print("Maybe you should copy `conf.py.example` to `conf.py`.")
        sys.exit(1)

    if options.contest_id is not None:
        install_proxy()
        if options.problem_id is not None:
            download_problem(options.contest_id, options.problem_id)
        else:
            download_contest(options.contest_id)
        sys.exit(0)

    if len(args) < 1 or not os.path.exists(args[0]):
        print("Source code not exist!")
        sys.exit(1)

    id, lang = os.path.splitext(args[0])
    executer = Executer(conf["ENV"][lang], id)

    ret = executer.compile()

    if ret != 0:
        print(">>> failed to Compile the source code!")
        sys.exit(1)

    with open("{0}{1}".format(id, conf["EXTENSION"])) as test_file:
        samples = etree.fromstring("<samples>{0}</samples>".format(test_file.read()))
        nodes = samples.getchildren()
        for case in range(len(nodes) // 2):
            input_text = nodes[case * 2].text[1:-1]
            answer_text = nodes[case * 2 + 1].text[1:-1]
            handle_test(executer, case, input_text, answer_text)


if __name__ == "__main__":
    main()
