"""Regression tests pinning each documented mislabel as fixed.

Every assertion here corresponds to a defect recorded in
docs/superpowers/specs/2026-11-08-ploppy-research-tool-design.md §9.
"""

import pytest

from src.database import code_mappings as cm


class TestOfficeCodesWereMislabelled:
    """11/44/55 were "Special Designation/District/Office". They are Program A."""

    @pytest.mark.parametrize("code", ["11", "22", "33", "44", "55", "66"])
    def test_program_a_codes_say_program_a(self, code):
        assert "Program A" in cm.get_office_name(code)

    def test_the_old_wrong_labels_are_gone(self):
        assert set(cm.OFFICE_CODES.values()).isdisjoint(
            {"Special Designation", "Special District", "Special Office"}
        )

    def test_base_offices_still_resolve(self):
        assert cm.get_office_name("1") == "Mayor"
        assert cm.get_office_name("5") == "City Council"
        assert cm.get_office_name("IS") == "Independent Spender"


class TestScheduleTypesWereMislabelled:
    def test_m_is_receipt_adjustments_not_matchable(self):
        assert cm.get_schedule_description("M") == "Receipt Adjustments"

    def test_d_is_in_kind_not_expenditures(self):
        assert cm.get_schedule_description("D") == "In-Kind Contributions"

    def test_abc_is_monetary_contributions(self):
        assert cm.get_schedule_description("ABC") == "Monetary Contributions"

    @pytest.mark.parametrize("code", ["G", "N"])
    def test_schedules_present_in_the_data_but_missing_from_the_old_map(self, code):
        """G (54 rows) and N (771 rows) are in CFB's key and in the data, but the
        hand-typed map omitted them, so they resolved to Unknown. Deriving from the
        key fixes these for free -- this test only pins that it stayed fixed."""
        label = cm.get_schedule_description(code)
        assert label and not label.startswith("Unknown")

    def test_schedule_x_is_honestly_unknown(self):
        """X has 1,504 rows in the data and appears nowhere in CFB's key. An honest
        Unknown is the correct answer; inventing a label would be worse than none."""
        assert cm.get_schedule_description("X") == "Unknown Schedule (X)"


class TestPaymentMethodsWereWrongAndPartlyInvented:
    def test_real_codes(self):
        assert cm.get_payment_method(1) == "Cash"
        assert cm.get_payment_method(2) == "Check"
        assert cm.get_payment_method(3) == "Other"
        assert cm.get_payment_method(4) == "Credit Card"
        assert cm.get_payment_method(5) == "Money Order"
        assert cm.get_payment_method(0) == "Unknown"

    @pytest.mark.parametrize("fabricated", [1253, 1530, 7686, 8012, 9253, 11, 15])
    def test_fabricated_codes_are_gone(self, fabricated):
        assert fabricated not in cm.PAYMENT_METHODS


class TestCandidateClassBridgesKeyLabelsToDataCodes:
    @pytest.mark.parametrize("code,label", [
        ("P", "Participant"),
        ("NP", "Non-Participant"),
        ("UN", "Undetermined"),
        ("L", "Limited Participant"),
    ])
    def test_data_abbreviations_resolve_to_the_keys_labels(self, code, label):
        """The export column carries P/NP/UN, not the key's full labels.
        P alone is 1,962,546 rows."""
        assert cm.get_candidate_class_desc(code) == label

    def test_the_keys_own_labels_are_not_the_keys(self):
        """Guards the regression directly: keying by label would look fine in
        isolation and return Unknown for every real row."""
        assert "Participant" not in cm.CANDIDATE_CLASS


class TestBlankIsACodeNotAMissingValue:
    def test_null_exemptcd_resolves_to_the_documented_blank_code(self):
        """CFB documents "" as a code meaning Not Exempt, and the loader stores
        blank as NULL on 2,123,656 of 2,123,892 rows. Treating NULL as Unknown
        would mislabel 99.99% of the column."""
        from src.vocab import codes as _c
        assert _c.label("EXEMPTCD", None) == "Not Exempt"
        assert _c.label("EXEMPTCD", "") == "Not Exempt"
        assert _c.label("EXEMPTCD", "   ") == "Not Exempt"

    def test_null_still_unknown_where_blank_is_not_a_documented_code(self):
        """SCHEDULE documents no blank, so NULL must not borrow one."""
        from src.vocab import codes as _c
        assert _c.label("SCHEDULE", None) == "Unknown"


class TestContributorCodes:
    def test_pcomp_is_a_pac(self):
        assert cm.get_contributor_type("PCOMP") == "Political Action Committee"

    def test_pcomc_is_a_candidate_committee(self):
        assert cm.get_contributor_type("PCOMC") == "Candidate Committee"

    def test_empo_is_a_labor_union_not_an_employee_organization(self):
        """8,695 rows. The old label was a plausible-sounding paraphrase, which is
        the kind of wrong that survives review because nothing looks broken."""
        assert cm.get_contributor_type("EMPO") == "Labor Union"

    @pytest.mark.parametrize("code", ["CAN", "FAM", "SPO", "PCOMZ"])
    def test_previously_missing_codes_are_present(self, code):
        """17,290 rows between them had no label at all."""
        assert code in cm.CONTRIBUTOR_CODES

    @pytest.mark.parametrize("code", ["PCOM", "TRST", "ORG"])
    def test_codes_cfb_does_not_document_stay_honestly_unknown(self, code):
        """PCOM (8,483 rows), TRST (14) and ORG (1) appear in the data but in
        neither CFB's key nor the old map. Deriving from the key cannot invent a
        label for them, and should not: an explicit Unknown is the correct answer,
        and these are the rows a later plan has to decide how to present."""
        assert code not in cm.CONTRIBUTOR_CODES
        assert cm.get_contributor_type(code) == "Unknown"


class TestAdjustmentTypes:
    def test_cfbs_missing_semicolon_did_not_swallow_refund(self):
        assert cm.get_adjustment_type(1) == "Returned Check"
        assert cm.get_adjustment_type(2) == "Refund"
        assert cm.get_adjustment_type(5) == "Other"


class TestBoroughCodesWereAlreadyCorrect:
    @pytest.mark.parametrize(
        "code,name",
        [("M", "Manhattan"), ("K", "Brooklyn"), ("Q", "Queens"),
         ("X", "Bronx"), ("S", "Staten Island")],
    )
    def test_boroughs(self, code, name):
        assert cm.get_borough_name(code) == name

    def test_z_is_outside_the_city(self):
        assert cm.get_borough_name("Z") == "Outside New York City"


class TestUnknownCodesDegradeGracefully:
    def test_unknown_office(self):
        assert cm.get_office_name("ZZZ") == "Unknown (ZZZ)"

    def test_none_payment_method(self):
        assert cm.get_payment_method(None) == "Unknown"


class TestUnrelatedHelpersSurvived:
    def test_parse_election_cycle(self):
        assert cm.parse_election_cycle("2021") == (2021, "General")

    def test_is_individual_name(self):
        assert cm.is_individual_name("SMITH, JOHN") is True
        assert cm.is_individual_name("ACME HOLDINGS LLC") is False
