from cloudmesh.common.console import Console
from cloudmesh.common.debug import VERBOSE
from cloudmesh.shell.command import PluginCommand
from cloudmesh.shell.command import command


class OracleCommand(PluginCommand):

    # noinspection PyUnusedLocal
    @command
    def do_oracle(self, args, arguments):
        """
        ::

          Usage:
                oracle --file=FILE
                oracle list

          This command is jsut for testing.

          Arguments:
              FILE   a file name

          Options:
              -f      specify the file

        """
        arguments.FILE = arguments['--file'] or None

        VERBOSE(arguments)

        if arguments.FILE:
            print("option a")

        elif arguments.list:
            print("option b")

        Console.error("This is just a sample")
        return ""
