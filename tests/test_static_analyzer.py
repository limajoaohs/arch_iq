"""Regressoes do analisador estatico (falsos negativos encontrados em 2026-11-05)."""

from src.agents.nodes import AgentNodes
from src.terraform.static_analyzer import analyze_terraform


def _codes(tf: str) -> set:
    return {f["code"] for f in analyze_terraform(tf)["findings"]}


SG_SSH_OPEN = '''
resource "aws_security_group" "web" {
  name = "web"
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
'''


def test_indented_ingress_with_open_ssh_is_flagged():
    result = analyze_terraform(SG_SSH_OPEN)
    assert "sg_admin_open" in {f["code"] for f in result["findings"]}
    assert result["category_points"].get("SG", 0) == 0


def test_indented_ingress_only_https_is_not_flagged():
    tf = SG_SSH_OPEN.replace("= 22", "= 443")
    assert not {"sg_admin_open", "sg_port_open"} & _codes(tf)


def test_iam_wildcard_in_json_heredoc():
    tf = '''
resource "aws_iam_policy" "admin" {
  policy = <<EOF
{"Statement": [{"Effect": "Allow", "Action": "*", "Resource": ["*"]}]}
EOF
}
'''
    codes = _codes(tf)
    assert {"iam_wildcard_action", "iam_wildcard_resource"} <= codes
    assert analyze_terraform(tf)["category_points"].get("IAM", 0) == 0


def test_iam_wildcard_in_jsonencode():
    tf = '''
resource "aws_iam_policy" "admin" {
  policy = jsonencode({
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "*"]
      Resource = "*"
    }]
  })
}
'''
    assert {"iam_wildcard_action", "iam_wildcard_resource"} <= _codes(tf)


def test_iam_specific_actions_not_flagged():
    tf = '''
resource "aws_iam_policy" "ro" {
  policy = jsonencode({
    Statement = [{
      Action    = ["s3:Get*"]
      NotAction = "*"
      Resource  = "arn:aws:s3:::bucket/*"
    }]
  })
}
'''
    codes = _codes(tf)
    assert "iam_wildcard_action" not in codes
    assert "iam_wildcard_resource" not in codes


def _savings(tf: str) -> int:
    nodes = AgentNodes.__new__(AgentNodes)  # optimize_finops nao usa estado da instancia
    return nodes.optimize_finops({"raw_input": tf})["finops_audit"]["monthly_savings_pct"]


def test_savings_ignore_optimizations_already_in_use():
    tf = '''
resource "aws_instance" "app" {
  instance_type = "t4g.micro"
}
resource "aws_cloudfront_distribution" "cdn" {
  enabled = true
}
'''
    assert _savings(tf) == 0


def test_savings_count_opportunities():
    tf = '''
resource "aws_instance" "app" {
  instance_type = "t3.micro"
}
'''
    assert _savings(tf) == 12
