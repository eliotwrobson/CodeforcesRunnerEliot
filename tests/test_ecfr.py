from click.testing import CliRunner

from ecfr.ecfr import cli


class TestWeather:
    def test_cli(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
