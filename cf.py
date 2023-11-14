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
import typing as t
import urllib.request as ulr
from optparse import OptionParser

import click
import lxml.html as lh
import requests
from bs4 import BeautifulSoup
from colorama import Back, Fore, Style
from lxml import etree

# TODO use asciimatics for display

ProblemType = t.Literal["A", "B", "C", "D", "E", "F", "G", "H"]

CODEFORCES_URL = "http://codeforces.com"
CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0"}


class Executer(object):
    def __init__(self, env, id) -> None:
        self.env = env
        self.id = id

    def compile(self):
        if len(self.env["compile"]) == 0:
            return 0
        return subprocess.call(self.env["compile"].format(self.id), shell=True)

    def execute(self, input_str: str) -> tuple[str, str, int, float]:
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
        return (
            stdout_data.decode(),
            stderr_data.decode(),
            proc.returncode,
            end - start,
        )


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


def get_parser_for_page(
    contest_id: str, problem_id: str | None
) -> tuple[BeautifulSoup, str]:
    if problem_id is None:
        url_tuple = (CODEFORCES_URL, "contest", contest_id)
    else:
        url_tuple = (CODEFORCES_URL, "contest", contest_id, "problem", problem_id)

    contest_url = "/".join(url_tuple)
    req = requests.get(contest_url, headers=REQUEST_HEADERS)
    parser = BeautifulSoup(req.text, "lxml")

    return parser, contest_url


def get_problem_ids(contest_id: str) -> None:
    parser = get_parser_for_page()
    table_entries = parser.find("table", {"class": "problems"}).find_all(
        "td", {"class": "id"}
    )

    return [entry.text.strip() for entry in table_entries]


def make_xml_file_tree(parser: BeautifulSoup, url: str) -> etree.ElementTree:
    def prepare_test_case_string(strings: t.Iterable[str]) -> str:
        return "\n" + "\n".join(strings) + "\n"

    # Create the root element
    page = etree.Element("codeforces-problem")

    # Add the problem URL
    pageElement = etree.SubElement(page, "url")
    pageElement.text = url

    # Create the element holding all tests
    test_cases = etree.SubElement(page, "test-cases")

    for input_node, answer_node in zip(
        parser.find_all("div", {"class": "input"}),
        parser.find_all("div", {"class": "output"}),
    ):
        test_case = etree.SubElement(test_cases, "case")

        test_input = etree.SubElement(test_case, "input")
        test_input.text = prepare_test_case_string(input_node.find("pre").strings)

        test_output = etree.SubElement(test_case, "output")
        test_output.text = prepare_test_case_string(answer_node.find("pre").strings)

    # Return a new document tree
    doc_tree = etree.ElementTree(page)
    etree.indent(doc_tree, space="")
    return doc_tree


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option("-cfn", "--config-file-name", default="conf.json")
@click.pass_context
def cli(context: click.Context, config_file_name: str) -> None:
    context.ensure_object(dict)

    with open(config_file_name, "r") as f:
        conf = json.load(f)

    context.obj = conf


@cli.command(context_settings=CONTEXT_SETTINGS)
@click.option(
    "-c", "--contest-id", help="Contest ID to download.", type=int, required=True
)
@click.option(
    "-p",
    "--problem-id",
    help="Problem ID to download.",
    type=click.Choice(t.get_args(ProblemType), case_sensitive=False),
    default=None,
)
@click.pass_context
def download_problem(
    context: click.Context, contest_id: int, problem_id: ProblemType | None
) -> None:
    contest_id_str = str(contest_id)

    # First, make directory to store downloaded problems
    dirname = context.obj["CONTEST_FOLDER_NAME"]
    if not os.path.exists(dirname):
        os.mkdir(dirname)

    # Next, get problem IDs to download
    if problem_id is None:
        problem_ids = get_problem_ids(contest_id_str)
    else:
        problem_ids = [problem_id]

    # Now, do the download and put the files in the directory
    for curr_problem_id in problem_ids:
        parser, url = get_parser_for_page(contest_id_str, curr_problem_id)

        name = parser.find("div", {"class": "title"}).text[3:]
        problem_file_name = f"{curr_problem_id}.xml"
        filename = os.path.join(dirname, problem_file_name)

        # Check with user if they'd like to overwrite old file
        if os.path.isfile(filename):
            click.confirm(
                f"Problem {curr_problem_id} already exists in contest folder. Would you like to overwrite?",
                abort=True,
            )

        with open(filename, "wb") as f:
            doc = make_xml_file_tree(parser, url)
            doc.write(f, xml_declaration=True, encoding="utf-8")

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


def print_center_separated(
    target_str: str, width: int = 100, color_addons: list[str] = [], delim: str = "="
) -> None:
    rem_width = (width - len(target_str)) // 2
    side_thing = delim * (rem_width - 1)
    res = side_thing + " " + target_str + " " + side_thing

    if len(res) < width:
        res += delim

    addon_str = "".join(color_addons)
    print(addon_str + res + Style.RESET_ALL)


def handle_test(executer: Executer, case, input_text: str, answer_text: str) -> bool:
    """Returns true if case was successful."""
    output_text, stderr_data, return_code, time_taken = executer.execute(input_text)
    print_center_separated(
        f" Case #{case}: ({time_taken*1000:0.2f} ms) ", color_addons=[Fore.MAGENTA]
    )
    print("Result: ", end="")

    return_status = False

    # TODO add something to handle TLE cases
    if return_code != 0:
        print(Fore.RED + "Program did not terminate successfully!" + Style.RESET_ALL)
        print_center_separated("Captured Standard Error")
        print(stderr_data)

        print_center_separated("Captured Standard Out")
        print(output_text)
    elif output_text.strip() == answer_text.strip():
        print(Fore.GREEN + "Test case passed!" + Style.RESET_ALL)
        return_status = True
    else:
        print(
            Fore.RED
            + "Program output did not match expected output\n"
            + Style.RESET_ALL
        )
        print_center_separated("Captured Output")
        print(output_text)
        print_center_separated("Expected Output")
        print(answer_text)
        print()

    return return_status
    # TODO have some type of correct approximation
    # elif check_result(answer_text, output_text):
    #    result = "AC"
    # else:
    #    result = "WA"

    # if result != "EXACTLY":
    #    print_center_separated("Answer")
    #    print(answer_text)

    # TODO add CL option to prompt for next thing
    # if result != "EXACTLY":
    #    input("press enter to continue or <C-c> to leave.")


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
        # TODO the old version used a proxy, try reimplementing later?
        # install_proxy()
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
    nodes_iter = iter(nodes)
    total_cases = len(nodes) // 2
    num_successes = 0
    for case in range(total_cases):
        input_text = next(nodes_iter).text.strip()
        answer_text = next(nodes_iter).text.strip()
        success = handle_test(executer, case, input_text, answer_text)
        if success:
            num_successes += 1

    print_center_separated("Summary")
    print(f"{num_successes} test cases out of {total_cases} passed.")
    print_center_separated("End of Results")


if __name__ == "__main__":
    cli()
    # download_problem()
    # main()
