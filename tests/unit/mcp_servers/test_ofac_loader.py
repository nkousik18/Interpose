"""Unit tests for mcp-servers/ofac-sanctions/src/loader.py -- pure parsing/matching
functions, no network. Fixture rows are drawn from real (public-domain) OFAC SDN
data to exercise the actual quirks documented in data/README.md: no header row, the
`-0-` null sentinel (including as a stand-in for sdn_type == "entity"), and a
bracket-joined multi-program field.
"""

from loader import best_match, build_index, parse_alt_csv, parse_sdn_csv, top_matches

# ent_num, name, sdn_type, program, title, call_sign, vess_type, tonnage, grt,
# vess_flag, vess_owner, remarks -- real rows (36, 306, 3751), one synthetic
# individual (99999) and one synthetic vessel (88888) added to exercise entity_type
# filtering.
SDN_CSV = """\
36,"AEROCARIBBEAN AIRLINES",-0- ,"CUBA",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0-
306,"BANCO NACIONAL DE CUBA",-0- ,"CUBA",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,"a.k.a. 'BNC'."
3751,"MOA NICKEL SA",-0- ,"CUBA] [CUBA-EO14404",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0-
99999,"DOE, John",individual,"SDGT",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0-
88888,"SS EXAMPLE",vessel,"CUBA",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0-

"""

# ent_num, alt_num, alt_type, alt_name, alt_remarks
ALT_CSV = """\
306,220,"aka","NATIONAL BANK OF CUBA",-0-
99999,1,"aka","Johnny Doe",-0-
77777,1,"aka","NOBODY (unknown ent_num)",-0-

"""


def test_parse_sdn_csv_parses_real_rows():
    entries = parse_sdn_csv(SDN_CSV)

    assert len(entries) == 5
    aerocaribbean = entries["36"]
    assert aerocaribbean.name == "AEROCARIBBEAN AIRLINES"
    assert aerocaribbean.programs == ["CUBA"]
    assert aerocaribbean.remarks == ""


def test_blank_sdn_type_means_entity():
    entries = parse_sdn_csv(SDN_CSV)
    assert entries["36"].sdn_type == "entity"
    assert entries["99999"].sdn_type == "individual"
    assert entries["88888"].sdn_type == "vessel"


def test_multi_program_field_splits_on_bracket_join():
    entries = parse_sdn_csv(SDN_CSV)
    assert entries["3751"].programs == ["CUBA", "CUBA-EO14404"]


def test_remarks_sentinel_becomes_empty_string():
    entries = parse_sdn_csv(SDN_CSV)
    assert entries["36"].remarks == ""
    assert entries["306"].remarks == "a.k.a. 'BNC'."


def test_short_trailing_row_is_skipped():
    # The real export ends with a stray DOS end-of-file marker (0x1A) on its own
    # line -- a 1-field row, not a 12-field one. SDN_CSV's fixture blank line
    # exercises the same "row shorter than 12 fields gets skipped" path.
    entries = parse_sdn_csv(SDN_CSV)
    assert "" not in entries
    assert len(entries) == 5


def test_parse_alt_csv_attaches_aliases_to_matching_entries():
    entries = parse_sdn_csv(SDN_CSV)
    parse_alt_csv(ALT_CSV, entries)

    assert entries["306"].aliases == ["NATIONAL BANK OF CUBA"]
    assert entries["99999"].aliases == ["Johnny Doe"]
    assert entries["36"].aliases == []


def test_parse_alt_csv_skips_unknown_ent_num():
    entries = parse_sdn_csv(SDN_CSV)
    # Should not raise even though ent_num 77777 isn't in `entries`.
    parse_alt_csv(ALT_CSV, entries)
    assert all(e.ent_num != "77777" for e in entries.values())


def test_build_index_names_by_type_filters_correctly():
    index = build_index(SDN_CSV, ALT_CSV)

    assert "DOE, John" in index.names_by_type["individual"]
    assert "DOE, John" not in index.names_by_type.get("vessel", {})
    assert "SS EXAMPLE" in index.names_by_type["vessel"]


def test_build_index_all_names_includes_aliases():
    index = build_index(SDN_CSV, ALT_CSV)

    assert index.all_names["NATIONAL BANK OF CUBA"] == ["306"]
    assert index.all_names["BANCO NACIONAL DE CUBA"] == ["306"]


def test_best_match_finds_near_exact_name():
    index = build_index(SDN_CSV, ALT_CSV)
    names = index.names_by_type["entity"]

    match = best_match(names, index, "Aerocaribbean Airlines", threshold=70.0)

    assert match is not None
    assert match.entry_id == "36"
    assert match.is_match is True
    assert match.score > 90


def test_best_match_respects_threshold():
    index = build_index(SDN_CSV, ALT_CSV)
    names = index.names_by_type["entity"]

    match = best_match(names, index, "a completely unrelated query string", threshold=70.0)

    assert match is not None  # always returns the best candidate found...
    assert match.is_match is False  # ...but flags it as below threshold


def test_best_match_on_empty_names_returns_none():
    index = build_index(SDN_CSV, ALT_CSV)
    assert best_match({}, index, "anything", threshold=70.0) is None


def test_check_alias_style_search_finds_entry_via_alias_name():
    index = build_index(SDN_CSV, ALT_CSV)

    matches = top_matches(index.all_names, index, "National Bank of Cuba", threshold=70.0, limit=3)

    assert any(m.entry_id == "306" for m in matches)
