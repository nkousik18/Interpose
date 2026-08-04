"""Unit tests for `interpose demo aml` (Phase 3 Day 15) -- the command's own
sequencing logic (which subprocess runs when, error propagation, audit verification
after a successful run), with `subprocess.run` and the audit query both mocked out.
Real end-to-end behavior (a genuine `dev-up.sh` cluster, a genuine investigation
run against a live gateway) is exercised manually, the same "verify live, don't just
unit-test" split every other Spark/CLI piece in this project follows -- spinning up
a real kind cluster or a real Postgres-backed investigation run in every CI build
would be far too slow and heavy for what a unit test is for.
"""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from interpose.audit.chain import ChainVerificationResult
from interpose.cli.main import app

runner = CliRunner()


def test_no_flags_is_an_error() -> None:
    result = runner.invoke(app, ["demo", "aml"])
    assert result.exit_code == 2
    assert "Specify --setup, --run" in result.output


class TestSetup:
    def test_invokes_dev_up_script(self) -> None:
        with patch("interpose.cli.demo.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(app, ["demo", "aml", "--setup"])

        assert result.exit_code == 0
        args, kwargs = mock_run.call_args
        assert str(args[0][0]).endswith("dev-up.sh")

    def test_propagates_a_nonzero_exit_code(self) -> None:
        with patch("interpose.cli.demo.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=17)
            result = runner.invoke(app, ["demo", "aml", "--setup"])

        assert result.exit_code == 17

    def test_does_not_also_run_an_investigation(self) -> None:
        with patch("interpose.cli.demo.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            runner.invoke(app, ["demo", "aml", "--setup"])

        assert mock_run.call_count == 1


class TestRun:
    def _ok_chain(self):
        return ChainVerificationResult(valid=True, checked=3)

    def test_invokes_the_investigator_script_with_the_gateway_url(self) -> None:
        with (
            patch("interpose.cli.demo.subprocess.run") as mock_run,
            patch("interpose.cli.demo.fetch_all_entries", return_value=[{"id": 1}]),
            patch("interpose.cli.demo.verify_chain", return_value=self._ok_chain()),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(app, ["demo", "aml", "--run"])

        assert result.exit_code == 0
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert str(cmd[1]).endswith("run_investigation.py")
        assert "--gateway-url" in cmd
        assert "http://127.0.0.1:8000" in cmd

    def test_passes_through_a_custom_account_id_and_gateway_url(self) -> None:
        with (
            patch("interpose.cli.demo.subprocess.run") as mock_run,
            patch("interpose.cli.demo.fetch_all_entries", return_value=[{"id": 1}]),
            patch("interpose.cli.demo.verify_chain", return_value=self._ok_chain()),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            runner.invoke(
                app,
                [
                    "demo",
                    "aml",
                    "--run",
                    "--account-id",
                    "1:ACC001",
                    "--gateway-url",
                    "http://example.test:9000",
                ],
            )

        cmd = mock_run.call_args.args[0]
        assert "--account-id" in cmd
        assert "1:ACC001" in cmd
        assert "http://example.test:9000" in cmd

    def test_investigation_failure_skips_audit_verification(self) -> None:
        with (
            patch("interpose.cli.demo.subprocess.run") as mock_run,
            patch("interpose.cli.demo.fetch_all_entries") as mock_fetch,
        ):
            mock_run.return_value = MagicMock(returncode=3)
            result = runner.invoke(app, ["demo", "aml", "--run"])

        assert result.exit_code == 3
        mock_fetch.assert_not_called()

    def test_no_audit_entries_is_an_error(self) -> None:
        with (
            patch("interpose.cli.demo.subprocess.run") as mock_run,
            patch("interpose.cli.demo.fetch_all_entries", return_value=[]),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(app, ["demo", "aml", "--run"])

        assert result.exit_code == 1
        assert "No audit entries found" in result.output

    def test_a_broken_chain_reports_failure(self) -> None:
        broken = ChainVerificationResult(valid=False, checked=2, first_mismatch_id=5)
        with (
            patch("interpose.cli.demo.subprocess.run") as mock_run,
            patch("interpose.cli.demo.fetch_all_entries", return_value=[{"id": 1}]),
            patch("interpose.cli.demo.verify_chain", return_value=broken),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(app, ["demo", "aml", "--run"])

        assert result.exit_code == 1
        assert "FAILED" in result.output
        assert "id=5" in result.output

    def test_a_valid_chain_reports_success_and_the_grafana_hint(self) -> None:
        with (
            patch("interpose.cli.demo.subprocess.run") as mock_run,
            patch("interpose.cli.demo.fetch_all_entries", return_value=[{"id": 1}]),
            patch("interpose.cli.demo.verify_chain", return_value=self._ok_chain()),
        ):
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(app, ["demo", "aml", "--run"])

        assert result.exit_code == 0
        assert "OK: chain intact" in result.output
        assert "Grafana" in result.output
