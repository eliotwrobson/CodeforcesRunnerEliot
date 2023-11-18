#! /usr/bin/env python2
# -*- coding: utf-8 -*-

import json
import math
import os
import subprocess
import sys
import time
import typing as t

import bs4
import click
import requests
from colorama import Fore, Style
from lxml import etree

# TODO use asciimatics for display

ProblemType = t.Literal["A", "B", "C", "D", "E", "F", "G", "H"]

CODEFORCES_URL = "http://codeforces.com"
CONTEXT_SETTINGS = dict(
    help_option_names=["-h", "--help"], show_default=True, max_content_width=120
)
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0"}


class Executer(object):
    def __init__(self, env: dict[str, str], problem_id: str, directory: str) -> None:
        self.env = env
        self.problem_id = problem_id
        self.directory = directory

    def compile(self) -> int:
        # TODO fix compile command for other languages
        if len(self.env["compile"]) == 0:
            return 0
        return subprocess.call(self.env["compile"].format(self.problem_id), shell=True)

    def execute(self, input_str: str) -> tuple[str, str, int, float]:
        run_command = self.env["execute"].format(
            problem_directory=self.directory, problem_id=self.problem_id
        )
        proc = subprocess.Popen(
            run_command,
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


def get_parser_for_page(
    contest_id: int, problem_id: str | None = None
) -> tuple[bs4.BeautifulSoup, str]:
    if problem_id is None:
        url_tuple: tuple[str, ...] = (CODEFORCES_URL, "contest", str(contest_id))
    else:
        url_tuple = (
            CODEFORCES_URL,
            "contest",
            str(contest_id),
            "problem",
            problem_id,
        )

    contest_url = "/".join(url_tuple)
    req = requests.get(contest_url, headers=REQUEST_HEADERS)
    parser = bs4.BeautifulSoup(req.text, "lxml")

    return parser, contest_url


def get_problem_ids(contest_id: int) -> list[str]:
    parser, _ = get_parser_for_page(contest_id)
    table = parser.find("table", {"class": "problems"})

    if not isinstance(table, bs4.Tag):
        raise Exception(f"Web scraping for contest {contest_id} failed!")

    table_entries = table.find_all("td", {"class": "id"})
    return [entry.text.strip() for entry in table_entries]


def make_xml_file_tree(parser: bs4.BeautifulSoup, url: str) -> etree.ElementTree:
    def prepare_test_case_string(strings: t.Iterable[str]) -> str:
        return "\n" + "\n".join(strings).strip() + "\n"

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
@click.option(
    "-cfn",
    "--config-file-name",
    default="conf.json",
    help="Name of config file to use.",
)
@click.pass_context
def cli(context: click.Context, config_file_name: str) -> None:
    context.ensure_object(dict)

    with open(config_file_name, "r") as f:
        conf = json.load(f)

    context.obj = conf


@cli.command(
    "dc",
    help="Download contest or individual problems",
    context_settings=CONTEXT_SETTINGS,
)
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
def download_contest(
    context: click.Context, contest_id: int, problem_id: ProblemType | None
) -> None:
    # contest_id_str = str(contest_id)

    # First, make directory to store downloaded problems
    dirname = context.obj["CONTEST_FOLDER_NAME"]
    if not os.path.exists(dirname):
        os.mkdir(dirname)

    # Next, get problem IDs to download
    if problem_id is None:
        problem_ids = get_problem_ids(contest_id)
        # In the case we download a whole contest, we want the problem directory to
        # be empty. So if it is not, we ask the user if they want us to wipe it.
        current_contest_files = os.listdir(dirname)
        if current_contest_files:
            click.confirm(
                f'Downloading contest {contest_id} will delete all problems in contest directory "{dirname}". '
                "Do you wish to continue?",
                abort=True,
            )

            for f in current_contest_files:
                file_name = os.path.join(dirname, f)
                print(f'Problem file "{file_name}" deleted.')
                os.remove(file_name)

    else:
        problem_ids = [problem_id]

    # Now, do the download and put the files in the directory
    for curr_problem_id in problem_ids:
        parser, url = get_parser_for_page(contest_id, curr_problem_id)

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


@cli.command("r", context_settings=CONTEXT_SETTINGS)
@click.argument("problem_id")
@click.pass_context
def run(context: click.Context, problem_id: str) -> None:
    """
    Run code against contest problems.

    PROBLEM_ID is the problem to run in the current folder.
    Source file to run determined based on file name.
    Looks in the source folder, determined in the config.
    """
    # filepath = os.path.join(, filename)
    source_folder = context.obj["SOURCE_FOLDER_NAME"]
    problem_name = problem_id.upper()
    code_file_names = [
        f
        for f in os.listdir(source_folder)
        if os.path.splitext(f)[0].upper() == problem_name
    ]

    if len(code_file_names) != 1:
        if len(code_file_names) > 1:
            print(
                f"Multiple source files found for problem {problem_name} "
                f'in directory "{source_folder}": {",".join(code_file_names)}'
            )
        else:
            print(
                f"No compatible source file found for problem {problem_name} "
                f'in directory "{source_folder}".'
            )

    filename = code_file_names[0]

    lang = os.path.splitext(filename)[1]
    executer = Executer(context.obj["ENV"][lang], problem_id, source_folder)

    ret = executer.compile()

    if ret != 0:
        print(">>> failed to Compile the source code!")
        sys.exit(1)

    test_file_name = os.path.join(
        context.obj["CONTEST_FOLDER_NAME"], f"{problem_name}.xml"
    )
    with open(test_file_name) as test_file:
        tests = bs4.BeautifulSoup(test_file, "xml")

    cases = tests.find("test-cases").find_all("case")
    num_successes = 0
    for i, case in enumerate(cases):
        input_text = case.find("input").text.strip()
        answer_text = case.find("output").text.strip()
        success = handle_test(executer, i, input_text, answer_text)
        if success:
            num_successes += 1

    print_center_separated("Summary")
    print(f"{num_successes} test cases out of {len(cases)} passed.")
    print_center_separated("End of Results")

    exit_code = 0 if num_successes == len(cases) else 1
    sys.exit(exit_code)


"""
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
"""


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


if __name__ == "__main__":
    cli()
