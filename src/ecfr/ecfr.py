#! /usr/bin/env python2
# -*- coding: utf-8 -*-

import json
import os
import shutil
import subprocess
import sys
import time
import typing as t
from importlib.resources import files

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
    def __init__(
        self,
        *,
        compile_command: t.Optional[str],
        execute_command: str,
        problem_id: str,
        source_file_dir: str,
        executable_file_dir: str,
        extension: str,
        timeout: int,
    ) -> None:
        self.compile_command = compile_command
        self.execute_command = execute_command
        self.source_file = os.path.join(source_file_dir, problem_id + "." + extension)
        self.output_file = os.path.join(executable_file_dir, problem_id)
        self.timeout = timeout

    def compile(self) -> subprocess.CompletedProcess:
        # TODO fix compile command for other languages
        if self.compile_command is None:
            raise ValueError("No compile command was set.")

        compile_command = self.compile_command.format(
            output_file=self.output_file, source_file=self.source_file
        )

        # TODO maybe set to capture output if I figure out how to preserve the colors
        return subprocess.run(
            compile_command,
            shell=True,
        )

    def execute(self, input_str: str) -> t.Tuple[str, str, int, float, bool]:
        """Execute the subprocess. Returns None in case of a timeout"""
        execute_command = self.execute_command.format(
            output_file=self.output_file, source_file=self.source_file
        )
        proc = subprocess.Popen(
            execute_command,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        start = time.perf_counter()
        tle = False
        output_str = ""
        err_str = ""
        return_code = 0

        try:
            (stdout_data, stderr_data) = proc.communicate(
                input=bytes(input_str, "utf-8"), timeout=self.timeout
            )
            proc.wait()
            end = time.perf_counter()

            # Set variables
            output_str = stdout_data.decode()
            err_str = stderr_data.decode()
            return_code = proc.returncode
        except subprocess.TimeoutExpired:
            tle = True
            end = start + self.timeout

        return (
            output_str,
            err_str,
            return_code,
            end - start,
            tle,
        )


def get_parser_for_page(
    contest_id: int, problem_id: t.Optional[str] = None
) -> t.Tuple[bs4.BeautifulSoup, str]:
    if problem_id is None:
        url_tuple: t.Tuple[str, ...] = (CODEFORCES_URL, "contest", str(contest_id))
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


def get_problem_ids(contest_id: int) -> t.List[str]:
    parser, _ = get_parser_for_page(contest_id)
    table = parser.find("table", {"class": "problems"})

    if not isinstance(table, bs4.Tag):
        raise Exception(f"Web scraping for contest {contest_id} failed!")

    table_entries = table.find_all("td", {"class": "id"})
    return [entry.text.strip() for entry in table_entries]


def make_xml_file_tree(parser: bs4.BeautifulSoup, url: str) -> etree._ElementTree:
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

    if os.path.isfile(config_file_name):
        with open(config_file_name, "r") as f:
            conf = json.load(f)

        context.obj = conf


@cli.command(
    "dc",
    context_settings=CONTEXT_SETTINGS,
)
@click.argument("contest_id", type=int)
@click.option(
    "-p",
    "--problem-id",
    help="Problem ID to download.",
    type=click.Choice(t.get_args(ProblemType), case_sensitive=False),
    default=None,
)
@click.pass_context
def download_contest(
    context: click.Context, contest_id: int, problem_id: t.Optional[ProblemType]
) -> None:
    """
    Download contest or individual problems.

    CONTEST_ID argument is the contest id to download. The whole contest
    will be downloaded into a directory as specified in the config file.
    To only download an individual problem, use the -p flag.
    """

    # First, make directory to store downloaded problems
    dirname = context.obj["CONTEST_DIRECTORY"]
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
                f"Downloading contest {contest_id} will delete all problems in "
                f'contest directory "{dirname}". Do you wish to continue?',
                abort=True,
            )

            for f in current_contest_files:
                file_name = os.path.join(dirname, f)
                print(f'Problem file "{file_name}" deleted.')
                os.remove(file_name)

    else:
        problem_ids = [problem_id.upper()]

    # Now, do the download and put the files in the directory
    for curr_problem_id in problem_ids:
        parser, url = get_parser_for_page(contest_id, curr_problem_id)

        name_tag = parser.find("div", {"class": "title"})

        name = (
            name_tag.text[3:] if name_tag is not None else f"Problem {curr_problem_id}"
        )
        problem_file_name = f"{curr_problem_id}.xml"
        filename = os.path.join(dirname, problem_file_name)

        # Check with user if they'd like to overwrite old file
        if os.path.isfile(filename):
            click.confirm(
                f"Problem {curr_problem_id} already exists in contest folder. "
                "Would you like to overwrite?",
                abort=True,
            )

        with open(filename, "wb") as f:
            doc = make_xml_file_tree(parser, url)
            doc.write(f, xml_declaration=True, encoding="utf-8")

        print(
            f'contest="{contest_id}", id="{curr_problem_id}", problem="{name}" '
            "is downloaded."
        )


@cli.command("r", context_settings=CONTEXT_SETTINGS)
@click.argument(
    "problem_id", type=click.Choice(t.get_args(ProblemType), case_sensitive=False)
)
@click.pass_context
def run(context: click.Context, problem_id: ProblemType) -> None:
    """
    Run code against contest problems.

    The first argument is the problem id to run in the current folder.
    Source file to run determined based on file name.
    Looks in the source folder, determined in the config.
    """

    # First, check for unique source file
    source_folder = context.obj["SOURCE_DIRECTORY"]
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

    # Get folder to put executables
    executable_folder = context.obj["EXECUTABLE_DIRECTORY"]
    if not os.path.exists(executable_folder):
        os.mkdir(executable_folder)

    # Create executor and do compilation if necessary.
    lang = os.path.splitext(filename)[1][1:]
    executer = Executer(
        compile_command=context.obj["ENV"][lang].get("compile"),
        execute_command=context.obj["ENV"][lang]["execute"],
        problem_id=problem_id,
        source_file_dir=source_folder,
        executable_file_dir=executable_folder,
        extension=lang,
        timeout=int(context.obj["TIMEOUT"]),
    )

    if executer.compile_command is not None:
        print("Starting Compilation")
        compile_res = executer.compile()

        if compile_res.returncode != 0:
            print(f"Compilation failed for problem {problem_id}.")
            print("Compilation Command:")
            print(compile_res.args)
            sys.exit(1)

        else:
            print(f"Compilation successful for problem {problem_id}.")

    # Open test case file
    test_file_name = os.path.join(
        context.obj["CONTEST_DIRECTORY"], f"{problem_name}.xml"
    )
    with open(test_file_name) as test_file:
        tests = bs4.BeautifulSoup(test_file, "xml")

    test_cases = tests.find("test-cases")

    if not isinstance(test_cases, bs4.Tag):
        raise Exception(f'Could not parse test cases from "{test_file_name}"')

    # Finally, execute all test cases and print summary
    cases = test_cases.find_all("case")
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


def print_center_separated(
    target_str: str, width: int = 100, color_addons: t.List[str] = [], delim: str = "="
) -> None:
    rem_width = (width - len(target_str)) // 2
    side_thing = delim * (rem_width - 1)
    res = side_thing + " " + target_str + " " + side_thing

    if len(res) < width:
        res += delim

    addon_str = "".join(color_addons)
    print(addon_str + res + Style.RESET_ALL)


def handle_test(
    executer: Executer, case: int, input_text: str, answer_text: str
) -> bool:
    """Returns true if case was successful."""
    (
        output_text,
        stderr_data,
        return_code,
        time_taken,
        time_limit_exceed,
    ) = executer.execute(input_text)
    print_center_separated(
        f" Case #{case}: ({time_taken*1000:0.2f} ms) ", color_addons=[Fore.MAGENTA]
    )
    print("Result: ", end="")

    return_status = False

    if return_code != 0:
        print(Fore.RED + "Program did not terminate successfully!" + Style.RESET_ALL)
        print_center_separated("Captured Standard Error")
        print(stderr_data)

        print_center_separated("Captured Standard Out")
        print(output_text)
    elif time_limit_exceed:
        print(Fore.YELLOW + "Time limit exceeded!" + Style.RESET_ALL)
    # TODO this direct equality is OK for most problem types, but may be an issue for
    # problems that deal with floating point numbers. Deal with this use case.
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


@cli.command("sp", context_settings=CONTEXT_SETTINGS)
@click.argument(
    "problem_id", type=click.Choice(t.get_args(ProblemType), case_sensitive=False)
)
@click.argument("language")
@click.pass_context
def start_problem(
    context: click.Context, problem_id: ProblemType, language: str
) -> None:
    """
    Create an empty solution file from a starter file in the source files
    folder.

    The first argument is the problem to create the starter file for.
    LANGUAGE is the file extension of the desired starter file.
    """

    problem_name = problem_id.upper()

    # Check if we can get the desired starter file.
    starter_files_dir = context.obj["STARTER_DIRECTORY"]
    starter_file_path = os.path.join(starter_files_dir, f"starter.{language}")

    if not os.path.isfile(starter_file_path):
        print(f'Starter file "{starter_file_path}" not found.')
        sys.exit(1)

    source_folder = context.obj["SOURCE_DIRECTORY"]

    filename = problem_name + "." + language
    desired_file_path = os.path.join(source_folder, filename)

    # Check with user if they'd like to overwrite old file
    if os.path.isfile(desired_file_path):
        click.confirm(
            f'Source file "{filename}" already exists in source directory '
            f'"{source_folder}". Would you like to overwrite?',
            abort=True,
        )

    # Make the empty source directory if it doesn't already exist.
    if not os.path.exists(source_folder):
        os.mkdir(source_folder)

    # Finally, copy the file.
    shutil.copy(starter_file_path, desired_file_path)

    print(f'New source file "{desired_file_path}" has been created.')


@cli.command("init", context_settings=CONTEXT_SETTINGS)
def init() -> None:
    """Copy example files into the current working directory."""

    example_dir = os.path.join(str(files("ecfr")), "example")
    current_dir = os.getcwd()
    copy_loc = shutil.copytree(
        example_dir,
        current_dir,
        dirs_exist_ok=True,
        ignore=lambda _, names: [name for name in names if name.startswith("__")],
    )

    print(f'Copied example directory into "{copy_loc}"')
