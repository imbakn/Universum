# -*- coding: UTF-8 -*-

import json
import shutil
import sh

from ...lib import utils
from ...lib.gravity import Dependency
from ...lib.utils import make_block
from .. import artifact_collector
from ..api_support import ApiSupport
from ..project_directory import ProjectDirectory
from ..structure_handler import needs_structure
from . import git_vcs, gerrit_vcs, perforce_vcs, local_vcs, base_vcs

__all__ = [
    "MainVcs",
    "PollVcs",
    "SubmitVcs"
]


def create_vcs(class_type=None):
    if class_type == "submit":
        p4_driver_factory_class = perforce_vcs.PerforceSubmitVcs
        git_driver_factory_class = git_vcs.GitSubmitVcs
        gerrit_driver_factory_class = gerrit_vcs.GerritSubmitVcs
        local_driver_factory_class = base_vcs.BaseSubmitVcs
    elif class_type == "poll":
        p4_driver_factory_class = perforce_vcs.PerforcePollVcs
        git_driver_factory_class = git_vcs.GitPollVcs
        gerrit_driver_factory_class = git_vcs.GitPollVcs
        local_driver_factory_class = base_vcs.BasePollVcs
    else:
        p4_driver_factory_class = perforce_vcs.PerforceMainVcs
        git_driver_factory_class = git_vcs.GitMainVcs
        gerrit_driver_factory_class = gerrit_vcs.GerritMainVcs
        local_driver_factory_class = local_vcs.LocalMainVcs

    @needs_structure
    class Vcs(ProjectDirectory):
        local_driver_factory = Dependency(local_driver_factory_class)
        git_driver_factory = Dependency(git_driver_factory_class)
        gerrit_driver_factory = Dependency(gerrit_driver_factory_class)
        perforce_driver_factory = Dependency(p4_driver_factory_class)

        @staticmethod
        def define_arguments(argument_parser):
            parser = argument_parser.get_or_create_group("Source files")

            parser.add_argument("--vcs-type", "-vt", dest="type", default="p4",
                                choices=["none", "p4", "git", "gerrit"],
                                help="Select repository type to download sources from: Perforce ('p4', the default), "
                                     "Git ('git'), Gerrit ('gerrit') or a local directory ('none'). "
                                     "Gerrit uses Git parameters. Each VCS type has its own settings.")

        def __init__(self, *args, **kwargs):
            super(Vcs, self).__init__(*args, **kwargs)
            try:
                if self.settings.type == "none":
                    driver_factory = self.local_driver_factory
                elif self.settings.type == "git":
                    driver_factory = self.git_driver_factory
                elif self.settings.type == "gerrit":
                    driver_factory = self.gerrit_driver_factory
                else:
                    driver_factory = self.perforce_driver_factory
            except AttributeError:
                raise NotImplementedError()
            self.driver = driver_factory()

        @make_block("Finalizing")
        def finalize(self):
            self.driver.finalize()

    return Vcs


PollVcs = create_vcs("poll")
SubmitVcs = create_vcs("submit")


class MainVcs(create_vcs()):
    artifacts_factory = Dependency(artifact_collector.ArtifactCollector)
    api_support_factory = Dependency(ApiSupport)

    @staticmethod
    def define_arguments(argument_parser):
        parser = argument_parser.get_or_create_group("Source files")

        parser.add_argument("--report-to-review", action="store_true", dest="report_to_review", default=False,
                            help="Perform test build for code review system (e.g. Gerrit or Swarm).")

    def __init__(self, *args, **kwargs):
        super(MainVcs, self).__init__(*args, **kwargs)
        self.artifacts = self.artifacts_factory()
        self.api_support = self.api_support_factory()

        if self.settings.report_to_review:
            self.code_review = self.driver.code_review()

    def is_latest_review_version(self):
        if self.settings.report_to_review:
            return self.code_review.is_latest_version()
        return True

    @make_block("Preparing repository")
    def prepare_repository(self):
        status_file = self.artifacts.create_text_file("REPOSITORY_STATE.txt")

        self.driver.prepare_repository()

        status_file.write(self.driver.get_repo_status())

        status_file.write("\nFile list:\n\n")
        status_file.write(utils.trim_and_convert_to_unicode(sh.ls("-lR", self.settings.project_root)) + "\n")
        status_file.close()

        file_diff = self.driver.calculate_file_diff()
        self.api_support.add_file_diff(json.dumps(file_diff, indent=4))

    def clean_sources_silently(self):
        try:
            shutil.rmtree(self.settings.project_root)
        except OSError:
            pass

    @make_block("Revert repository")
    def revert_repository(self):
        diff = self.driver.copy_cl_files_and_revert()
        return diff
