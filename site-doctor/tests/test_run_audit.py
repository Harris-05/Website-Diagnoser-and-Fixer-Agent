"""Tests for run_audit.py, the non-interactive entry point.

Two things are worth testing without a browser:

  - argument handling, including the deliberate refusal of --checks security
  - that the headless graph actually COMPILES

The second matters because run_audit.py rewires Haris's nodes into a new
graph. A typo in a node name or a missing edge is a silent mistake that only
shows up at runtime, which in a container means a failed deploy.
"""

import pytest

import run_audit
from run_audit import _parse_args, _parse_checks


# ---- --checks parsing ----

def test_parse_checks_single():
    assert _parse_checks("seo") == ["seo"]


def test_parse_checks_normalises_case_and_whitespace():
    assert _parse_checks(" SEO , ux ") == ["seo", "ux"]


def test_parse_checks_refuses_security():
    """Not an oversight -- security_audit_node calls
    run_active_security_tests(), which raises PermissionError on any
    unverified domain and kills the run. Failing here gives a readable
    message instead of a traceback from three modules away."""
    with pytest.raises(ValueError, match="finding #1"):
        _parse_checks("seo,security")


def test_parse_checks_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown check"):
        _parse_checks("seo,performance")


def test_parse_checks_rejects_empty():
    with pytest.raises(ValueError, match="No checks selected"):
        _parse_checks("  ,  ")


# ---- argparse ----

def test_defaults_are_container_friendly():
    """Small defaults on purpose: a t3.micro has 1 GB of RAM and this app
    runs two browsers."""
    args = _parse_args(["--url", "https://site.com"])

    assert args.url == "https://site.com"
    assert args.checks == "seo"
    assert args.max_pages == 5
    assert args.max_depth == 1
    assert args.no_report is False


def test_url_is_required():
    with pytest.raises(SystemExit):
        _parse_args([])


# ---- graph wiring ----

@pytest.fixture
def fake_key(monkeypatch):
    """agent.graph imports fix/suggest.py, which builds an OpenAI client at
    import time -- so a value has to exist before the import. No network call
    is made by compiling a graph."""
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-key-no-calls-made")


def test_headless_graph_compiles(fake_key):
    app = run_audit.build_headless_graph(
        selected_checks=["seo"],
        max_depth=1,
        max_pages=2,
        want_report=True,
    )

    assert app is not None


def test_headless_graph_has_the_expected_nodes(fake_key):
    """Guards against a renamed node or a dropped edge. Note approve/apply/
    reaudit are intentionally absent -- all three are stubs returning {}."""
    app = run_audit.build_headless_graph(
        selected_checks=["seo", "ux"],
        max_depth=1,
        max_pages=2,
        want_report=True,
    )

    nodes = set(app.get_graph().nodes)

    for expected in ("config", "crawl", "seo_audit", "ux_review", "triage", "fix", "report"):
        assert expected in nodes

    assert "approve" not in nodes
    assert "apply" not in nodes
    assert "reaudit" not in nodes


def test_config_node_returns_values_instead_of_mutating_state():
    """Regression guard for the bug in CLAUDE.md section 4: LangGraph ignores
    in-place mutation of the state object and only reads what a node returns.
    check_selection_node originally set state.max_depth directly, so the typed
    values never reached crawl_node.

    No API key needed -- make_config_node lives above the agent.graph import."""
    from models.schemas import SiteDoctorState

    config_node = run_audit.make_config_node(["seo"], max_depth=3, max_pages=7)

    returned = config_node(SiteDoctorState(url="https://site.com"))

    assert returned == {
        "selected_checks": ["seo"],
        "max_depth": 3,
        "max_pages": 7,
    }


def test_report_node_skips_pdf_when_disabled():
    """--no-report must not call generate_report_pdf at all."""
    from models.schemas import SiteDoctorState

    report_node = run_audit.make_report_node(want_report=False)

    assert report_node(SiteDoctorState(url="https://site.com")) == {"report_path": None}


# ---- main() exit codes ----

def test_main_exits_2_when_security_requested(monkeypatch, capsys):
    monkeypatch.setattr(run_audit, "load_dotenv", lambda *a, **k: None)

    exit_code = run_audit.main(["--url", "https://site.com", "--checks", "security"])

    assert exit_code == 2
    assert "finding #1" in capsys.readouterr().err


def test_main_exits_2_without_an_api_key(monkeypatch, capsys):
    """A missing key must be one clear line, not an OpenAI constructor error
    raised from inside somebody else's import."""
    # neutralised so a developer's real .env cannot make this test pass
    monkeypatch.setattr(run_audit, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    exit_code = run_audit.main(["--url", "https://site.com"])

    assert exit_code == 2
    assert "OPENAI_API_KEY" in capsys.readouterr().err
