import json
from pathlib import Path

import pytest

from cockpit_core.appearance import (
    COCKPIT_CYAN,
    DEFAULT_MARGIN,
    AppearanceStore,
    CockpitAppearance,
    HexColor,
    default_config_path,
    normalized_title,
)


@pytest.fixture
def store(tmp_path):
    return AppearanceStore(tmp_path / "config.json")


@pytest.mark.parametrize("text", ["#FF3300", "ff3300", "  #Ff3300 "])
def test_parses_six_hex_digits_with_or_without_the_hash(text):
    assert HexColor.from_hex(text) == HexColor(1, 0.2, 0)


@pytest.mark.parametrize("text", ["", "#FFF", "#GG3300", "#FF33001", "red"])
def test_rejects_anything_that_is_not_six_hex_digits(text):
    assert HexColor.from_hex(text) is None


def test_writes_itself_as_uppercase_hex():
    assert HexColor(1, 0.2, 0).hex == "#FF3300"
    assert HexColor(0, 0, 0).hex == "#000000"


def test_components_outside_the_unit_range_are_clamped():
    assert HexColor(1.4, -0.2, 0.5).hex == "#FF0080"


def test_the_standard_accent_is_the_same_cyan_claude_cockpit_uses():
    assert COCKPIT_CYAN.hex == "#4FE8FF"
    assert HexColor.from_hex(COCKPIT_CYAN.hex) == COCKPIT_CYAN


def test_renders_itself_as_css():
    assert COCKPIT_CYAN.rgba() == "rgba(79, 232, 255, 1)"
    assert COCKPIT_CYAN.rgba(0.45) == "rgba(79, 232, 255, 0.45)"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("work", "WORK"),
        ("  work  ", "WORK"),
        ("", "GITHUB"),
        ("   ", "GITHUB"),
        ("a title longer than fourteen", "A TITLE LONGER"),
    ],
)
def test_titles_are_trimmed_capitalized_and_cut_to_fit_beside_the_status(raw, expected):
    assert normalized_title(raw) == expected


def test_cutting_a_title_never_leaves_a_trailing_space():
    assert normalized_title("abcdefghijklm nop") == "ABCDEFGHIJKLM"


def test_an_absent_config_file_gives_the_defaults(store):
    assert store.load() == CockpitAppearance()
    assert store.load_placement() == (DEFAULT_MARGIN, DEFAULT_MARGIN)


def test_an_appearance_survives_a_round_trip(store):
    chosen = CockpitAppearance(
        title="work",
        accent=HexColor.from_hex("#B6FF5C"),
        border=HexColor.from_hex("#FF4FD8"),
        glow=HexColor.from_hex("#FF9A3D"),
    )
    store.save(chosen)
    assert store.load() == chosen


def test_saving_the_appearance_keeps_the_position(store):
    store.save_placement(40, 20)
    store.save(CockpitAppearance(title="work"))
    assert store.load_placement() == (40, 20)
    assert store.load().title == "WORK"


def test_saving_the_position_keeps_the_appearance(store):
    store.save(CockpitAppearance(title="work"))
    store.save_placement(40, 20)
    assert store.load().title == "WORK"


def test_the_file_is_the_documented_shape_so_it_can_be_edited_by_hand(store):
    store.save(CockpitAppearance(title="work", accent=HexColor.from_hex("#B6FF5C")))
    assert json.loads(store.path.read_text()) == {
        "title": "WORK",
        "accentColor": "#B6FF5C",
        "borderColor": "#4FE8FF",
        "glowColor": "#4FE8FF",
    }


@pytest.mark.parametrize("text", ["not json", "", "[1, 2]", '"a string"'])
def test_an_unreadable_file_falls_back_to_the_defaults_rather_than_stopping_the_widget(store, text):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(text)
    assert store.load() == CockpitAppearance()
    assert store.load_placement() == (DEFAULT_MARGIN, DEFAULT_MARGIN)


def test_one_unreadable_color_falls_back_on_its_own(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps({"accentColor": "chartreuse", "borderColor": "#B6FF5C"}))

    appearance = store.load()
    assert appearance.accent == COCKPIT_CYAN
    assert appearance.border == HexColor.from_hex("#B6FF5C")


@pytest.mark.parametrize("value", ['"12"', "true", "null"])
def test_a_position_that_is_not_a_number_falls_back_to_the_default_margin(store, value):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text('{"marginTop": %s, "marginRight": 40}' % value)
    assert store.load_placement() == (DEFAULT_MARGIN, 40)


def test_a_half_written_file_is_never_left_behind(store):
    store.save(CockpitAppearance(title="work"))
    assert not list(store.path.parent.glob("*.tmp"))


def test_the_github_cli_is_gh_unless_the_file_names_another(store):
    assert store.load_cli_command() == "gh"

    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps({"cliCommand": "~/.local/bin/gh-work"}))
    assert store.load_cli_command() == "~/.local/bin/gh-work"


def test_no_account_is_chosen_until_one_is(store):
    assert store.account is None

    store.account = "work"
    assert store.account == "work"

    store.account = None
    assert store.account is None
    assert "account" not in json.loads(store.path.read_text())


def test_choosing_an_account_keeps_the_rest_of_the_file(store):
    store.save_placement(40, 20)
    store.account = "work"
    assert store.load_placement() == (40, 20)


@pytest.mark.parametrize("value", ['""', '"  "', "17", "true"])
def test_an_account_that_is_not_a_login_means_none_is_chosen(store, value):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{\"account\": %s}" % value)
    assert store.account is None


@pytest.mark.parametrize("value", ['""', '"  "', "17", "null", "true"])
def test_a_cli_command_that_is_not_a_name_falls_back_to_gh(store, value):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{\"cliCommand\": %s}" % value)
    assert store.load_cli_command() == "gh"


def test_saving_the_appearance_keeps_a_hand_edited_cli_command(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps({"cliCommand": "gh-work"}))

    store.save(CockpitAppearance(title="work"))
    assert store.load_cli_command() == "gh-work"


@pytest.mark.parametrize(
    "value, uses_the_variable",
    [("/tmp/xdg", True), ("relative/path", False), ("", False)],
)
def test_the_config_directory_ignores_an_empty_or_relative_xdg_config_home(
    monkeypatch, value, uses_the_variable
):
    # The XDG spec says a value that is unset, empty or relative is to be ignored.
    monkeypatch.setenv("XDG_CONFIG_HOME", value)

    path = default_config_path()

    assert path.is_absolute()
    assert path.is_relative_to(value) is uses_the_variable


def test_the_config_directory_falls_back_to_dot_config(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert default_config_path() == Path.home() / ".config/github-cockpit/config.json"


def test_reset_puts_the_look_back_to_the_defaults(store):
    store.save(
        CockpitAppearance(
            title="work",
            accent=HexColor.from_hex("#B6FF5C"),
            border=HexColor.from_hex("#FF4FD8"),
            glow=HexColor.from_hex("#FF9A3D"),
        )
    )
    store.reset()
    assert store.load() == CockpitAppearance()


def test_reset_leaves_the_position_the_account_and_the_cli_alone(store):
    # Reset to Defaults is about the look; it should not move the card or sign it out.
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps({"cliCommand": "gh-work"}))
    store.save_placement(40, 20)
    store.account = "work"
    store.save(CockpitAppearance(title="work"))

    store.reset()

    assert store.load_placement() == (40, 20)
    assert store.account == "work"
    assert store.load_cli_command() == "gh-work"


def test_reset_on_an_untouched_config_is_harmless(store):
    store.reset()
    assert store.load() == CockpitAppearance()


def test_the_personalize_window_is_offered_once(store):
    assert store.has_offered_customization is False

    store.has_offered_customization = True
    assert store.has_offered_customization is True
    # A second launch reads the same file and must not offer again.
    assert AppearanceStore(store.path).has_offered_customization is True


def test_being_offered_the_window_survives_a_later_save(store):
    store.has_offered_customization = True
    store.save(CockpitAppearance(title="work"))
    store.save_placement(40, 20)
    assert store.has_offered_customization is True


def test_resetting_the_look_does_not_make_the_window_offer_itself_again(store):
    store.has_offered_customization = True
    store.reset()
    assert store.has_offered_customization is True
