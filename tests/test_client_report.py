"""Relatorio para o cliente: linguagem de leigo, sem LLM e sem regras esquecidas."""
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from src.agents.client_report import FINDING_TO_RISK, RISKS, SAVINGS, build_client_report
from src.terraform.static_analyzer import analyze_terraform

ANALYZER = os.path.join(os.path.dirname(__file__), "..", "src", "terraform", "static_analyzer.py")

RISKY_TF = """
resource "aws_security_group" "web" {
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "web" {
  instance_type = "t3.medium"
}

resource "aws_s3_bucket" "uploads" {
  bucket = "uploads"
  acl    = "public-read"
}

resource "aws_db_instance" "app" {
  engine                  = "postgres"
  storage_encrypted       = false
  publicly_accessible     = true
  multi_az                = false
}
"""

# Termos que um cliente nao precisa conhecer para entender o relatorio
JARGON = re.compile(
    r"\b(S3|EC2|RDS|IAM|VPC|ALB|ELB|SG|ACL|CIDR|SSH|RDP|Multi-AZ|bucket|egress|ingress|"
    r"wildcard|finding|findings|CloudTrail|CloudWatch|Graviton|t3|t4g)\b",
    re.IGNORECASE,
)


def report_for(terraform):
    result = analyze_terraform(terraform)
    return build_client_report(
        result["score"], result["findings"], result["optimizations"], result["services"]
    )


def test_every_analyzer_finding_has_client_text():
    source = open(ANALYZER, encoding="utf-8").read()
    codes = set(re.findall(r'_add_finding\("(\w+)"', source))
    assert codes, "nenhum codigo encontrado no analisador"
    assert codes <= set(FINDING_TO_RISK)
    assert set(FINDING_TO_RISK.values()) <= set(RISKS)


def test_every_analyzer_optimization_has_client_text():
    source = open(ANALYZER, encoding="utf-8").read()
    codes = set(re.findall(r'"code": "(\w+)",\s+"status"', source))
    assert codes == set(SAVINGS)


def test_catalog_has_no_jargon():
    for copy in [*RISKS.values(), *SAVINGS.values()]:
        for text in copy.values():
            assert not JARGON.search(text), text


def test_report_text_has_no_jargon_or_resource_names():
    report = report_for(RISKY_TF)
    assert not JARGON.search(report["plain_text"]), JARGON.search(report["plain_text"])
    assert "uploads" not in report["plain_text"]


def test_risks_are_ordered_by_priority():
    risks = report_for(RISKY_TF)["risks"]
    priorities = [r["priority"] for r in risks]
    assert priorities == sorted(priorities)
    assert risks[0]["priority_label"] == "Resolver primeiro"


def test_same_problem_is_grouped_for_the_client():
    report = build_client_report(
        40,
        [
            {"code": "rds_no_multi_az", "severity": "MEDIUM"},
            {"code": "rds_single_az", "severity": "MEDIUM"},
        ],
        [],
        ["RDS"],
    )
    assert len(report["risks"]) == 1
    assert report["risks"][0]["occurrences"] == 2


def test_savings_in_use_are_not_sold_as_opportunities():
    report = build_client_report(
        80,
        [],
        [
            {"code": "graviton", "status": "in_use"},
            {"code": "migrate_graviton", "status": "opportunity"},
        ],
        ["EC2"],
    )
    assert [s["title"] for s in report["strengths"]] == [SAVINGS["graviton"]["title"]]
    assert [s["title"] for s in report["savings"]] == [SAVINGS["migrate_graviton"]["title"]]


@pytest.mark.parametrize(
    "score, findings, headline",
    [
        (95, [], "Em boa forma"),
        (80, [{"code": "s3_public_acl", "severity": "HIGH"}], "Boa, com pontos a resolver"),
        (60, [], "Pede ajustes"),
        (30, [], "Precisa de atenção"),
    ],
)
def test_headline_follows_score_and_urgent_risks(score, findings, headline):
    assert build_client_report(score, findings, [], ["S3"])["headline"] == headline


def test_unrecognized_input_does_not_claim_a_real_assessment():
    result = analyze_terraform("minha empresa tem um site")
    report = build_client_report(
        result["score"], result["findings"], result["optimizations"], ["GENERAL_AWS"]
    )
    assert report["headline"] == "Análise limitada"
    assert report["risks"] == []
    assert "não representa o sistema real" in report["summary"]
