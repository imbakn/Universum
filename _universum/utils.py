# -*- coding: UTF-8 -*-

import os
import os.path
import traceback
import sys
import codecs

from _universum.ci_exception import SilentAbortException
from .ci_exception import CriticalCiException

__all__ = [
    "Colors",
    "strip_path_start",
    "parse_path",
    "detect_environment",
    "create_diver",
    "format_traceback",
    "make_block",
    "catch_exception",
    "trim_and_convert_to_unicode",
    "unify_argument_list",
    "Uninterruptible"
]

# For proper unicode symbols processing
sys.stdout = codecs.getwriter("utf-8")(sys.stdout)


class Colors(object):
    red = "\033[1;31m"
    dark_red = "\033[0;31m"
    green = "\033[1;32m"
    blue = "\033[1;34m"
    dark_yellow = "\033[0;33m"
    reset = "\033[00m"


def strip_path_start(line):
    if line.startswith("./"):
        return line[2:]
    return line


def parse_path(path, starting_point):
    if path.startswith('/'):
        path = os.path.join(path)
    else:
        path = os.path.join(starting_point, path)

    return os.path.abspath(path)


def detect_environment():
    """
    :return: "tc" if the script is launched on TeamCity agent,
             "jenkins" is launched on Jenkins agent,
             "terminal" otherwise
    """
    teamcity = "TEAMCITY_VERSION" in os.environ
    jenkins = "JENKINS_HOME" in os.environ
    if teamcity and not jenkins:
        return "tc"
    if not teamcity and jenkins:
        return "jenkins"
    return "terminal"


def create_diver(local_factory, teamcity_factory, jenkins_factory, default=None):
    if default:
        env_type = default
    else:
        env_type = detect_environment()
    if env_type == "tc":
        return teamcity_factory()
    elif env_type == "jenkins":
        return jenkins_factory()
    return local_factory()


def format_traceback(ex, trace):
    tb_lines = traceback.format_exception(ex.__class__, ex, trace)
    tb_text = ''.join(tb_lines)
    return tb_text


def make_block(block_name, pass_errors=True):
    def decorated_function(function):
        def function_in_block(self, *args, **kwargs):
            return self.out.run_in_block(function, block_name, pass_errors, self, *args, **kwargs)
        return function_in_block
    return decorated_function


def catch_exception(exception, ignore_if=None):
    def decorated_function(function):
        def function_to_run(*args, **kwargs):
            result = None
            try:
                result = function(*args, **kwargs)
                return result
            except exception as e:
                if ignore_if is not None:
                    if ignore_if in unicode(e):
                        return result
                raise CriticalCiException(unicode(e))
        return function_to_run
    return decorated_function


def trim_and_convert_to_unicode(line):
    if isinstance(line, str):
        line = line.decode("utf-8")
    elif not isinstance(line, unicode):
        line = unicode(line)

    if line.endswith("\n"):
        line = line[:-1]

    return line


def unify_argument_list(source_list, separator=',', additional_list=None):
    if additional_list is None:
        resulting_list = []
    else:
        resulting_list = additional_list

    # Add arguments parsed by ModuleArgumentParser, including list elements generated by nargs='+'
    if source_list is not None:
        for item in source_list:
            if isinstance(item, list):
                resulting_list.extend(item)
            else:
                resulting_list.append(item)

    # Remove None and empty elements added by previous steps
    resulting_list = [item for item in resulting_list if item]

    # Split one-element arguments and merge to one list
    resulting_list = [item.strip() for entry in resulting_list for item in entry.strip('"\'').split(separator)]

    return resulting_list


class Uninterruptible(object):
    def __init__(self):
        self.return_code = 0
        self.exceptions = []

    def __enter__(self):
        def excepted_function(func, *args, **kwargs):
            try:
                func(*args, **kwargs)
            except SilentAbortException as e:
                self.return_code = max(self.return_code, e.application_exit_code)
            except Exception as e:
                ex_traceback = sys.exc_info()[2]
                self.exceptions.append(format_traceback(e, ex_traceback))
                self.return_code = max(self.return_code, 2)
        return excepted_function

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.return_code == 1:
            raise SilentAbortException()
        if self.return_code == 2:
            for entry in self.exceptions:
                sys.stderr.write(entry)
            raise SilentAbortException(application_exit_code=2)
