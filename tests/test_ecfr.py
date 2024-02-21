from click.testing import CliRunner

from ecfr.ecfr import cli

# TODO add more integration tests that directly call the command line


class TestECFR:
    def test_cli(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
