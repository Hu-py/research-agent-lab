import pytest
from research_agent_lab.frontier.bilingual_report import create_bilingual_report
from research_agent_lab.model import BudgetedModel


class FakeTranslator:
    last_usage = {"input_tokens":0, "output_tokens":0}
    def __init__(self, broken=False): self.broken=broken;self.calls=[]
    def complete(self, *, role, system, payload):
        self.calls.append((role,payload))
        assert role == "bilingual_research_editor"
        assert payload["verification"]["data_feasible_assessment"] is False
        if self.broken: return {"title":{"zh":"中文"}}
        return {k:{"zh":"研究证据仍不足","en":"Research evidence is insufficient"} for k in
                ("title","research_question","method","competition_insight",
                 "scientific_assessment","evidence_limitations")}


def case():
    return {"winner":{"id":"H003","title":"Scientific question","question":"Question",
                      "method":"Method"},
            "verification":{"data_feasible_assessment":False,
                            "novelty_verified":False,"experimental_claim_verified":False,
                            "evidence_limitations":["no access"]},
            "matches":[],"status":"needs_more_evidence"}


def test_bilingual_report_pairs_both_languages_without_marking_verified():
    fake=FakeTranslator()
    model=BudgetedModel(fake,max_calls=2)
    report=create_bilingual_report(case(),model)
    assert report["fields"]["title"]["en"]=="Research evidence is insufficient"
    assert report["novelty_verified"] is False
    assert report["experimental_claim_verified"] is False
    assert model.usage.calls==1


def test_translation_invalid_shape_does_not_fabricate_a_language():
    with pytest.raises(ValueError,match="BILINGUAL_LANGUAGE_MISSING|BILINGUAL_FIELD_INVALID"):
        create_bilingual_report(case(),BudgetedModel(FakeTranslator(broken=True)))
