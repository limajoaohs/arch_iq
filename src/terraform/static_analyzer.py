"""Analisador estatico de arquivos Terraform (.tf).

Inspeciona o codigo Terraform diretamente (sem depender de LLM / credenciais AWS)
para detectar recursos, verificar boas praticas de seguranca (Well-Architected)
e calcular um score numerico com findings específicos.

Modelo de pontuacao: pontos POSITIVOS por categoria de boa pratica.
Categorias e pesos:
  - Seguranca de rede (Security Groups):        20 pts
  - S3 (acl privada, Block Public Access, cripto): 20 pts
  - RDS (cripto, Multi-AZ, backup, nao publico):   15 pts
  - CloudTrail:                                  10 pts
  - AWS Config:                                  10 pts
  - CloudWatch:                                  10 pts
  - IAM (sem wildcard):                          10 pts
  - ELB/ALB (SSL/HTTPS):                          5 pts
  Total:                                       100 pts
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


class TerraformStaticAnalyzer:
    """Detecta recursos Terraform e aplica regras de seguranca/custo."""

    # Pesos por categoria (pontos MAXIMOS que cada categoria pode contribuir)
    WEIGHT_SG = 20
    WEIGHT_S3 = 20
    WEIGHT_RDS = 15
    WEIGHT_CLOUDTRAIL = 10
    WEIGHT_CONFIG = 10
    WEIGHT_CLOUDWATCH = 10
    WEIGHT_IAM = 10
    WEIGHT_ELB = 5

    def __init__(self) -> None:
        self.score: int = 0
        self.findings: List[Dict[str, str]] = []
        self.optimizations: List[Dict[str, str]] = []
        self.services: List[str] = []
        # Pontos ganhos por categoria (para relatorio detalhado)
        self.category_points: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_resource_blocks(text: str) -> List[Dict[str, str]]:
        blocks: List[Dict[str, str]] = []
        pattern = re.compile(
            r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{(.*?)\n\}',
            re.DOTALL,
        )
        for m in pattern.finditer(text):
            blocks.append({
                "type": m.group(1),
                "name": m.group(2),
                "body": m.group(3),
            })
        return blocks

    @staticmethod
    def _extract_ingress_blocks(body: str) -> List[str]:
        return re.findall(r"ingress\s*\{(.*?)\n\}", body, re.DOTALL)

    @staticmethod
    def _get_attr(body: str, attr: str) -> str | None:
        # Captura string com aspas ou valor numerico/booleano sem aspas
        m = re.search(rf'{re.escape(attr)}\s*=\s*"([^"]*)"', body)
        if m:
            return m.group(1)
        m = re.search(rf'{re.escape(attr)}\s*=\s*([0-9]+)', body)
        if m:
            return m.group(1)
        return None

    @staticmethod
    def _get_bool(body: str, attr: str) -> bool | None:
        m = re.search(rf'{re.escape(attr)}\s*=\s*(true|false)', body)
        if not m:
            return None
        return m.group(1) == "true"

    @staticmethod
    def _has_resource_type(text: str, rtype: str) -> bool:
        return bool(re.search(r'resource\s+"' + re.escape(rtype) + r'"', text))

    def _add_points(self, category: str, points: int) -> None:
        self.category_points[category] = self.category_points.get(category, 0) + points
        self.score += points

    def _add_finding(self, severity: str, service: str, rule: str, remediation: str) -> None:
        self.findings.append({
            "severity": severity,
            "service": service,
            "rule": rule,
            "remediation": remediation,
        })

    # ------------------------------------------------------------------
    # Analise principal
    # ------------------------------------------------------------------
    def analyze(self, text: str) -> Dict[str, Any]:
        self.score = 0
        self.findings = []
        self.optimizations = []
        self.services = []
        self.category_points = {}

        blocks = self._extract_resource_blocks(text)
        lower = text.lower()

        service_map = {
            "aws_vpc": "VPC",
            "aws_subnet": "VPC",
            "aws_security_group": "SECURITY_GROUP",
            "aws_s3_bucket": "S3",
            "aws_s3_bucket_public_access_block": "S3",
            "aws_db_instance": "RDS",
            "aws_db_subnet_group": "RDS",
            "aws_elasticache_replication_group": "ELASTICACHE",
            "aws_elasticache_subnet_group": "ELASTICACHE",
            "aws_lb": "ALB",
            "aws_elb": "ELB",
            "aws_cloudtrail": "CLOUDTRAIL",
            "aws_config_configuration_recorder": "CONFIG",
            "aws_cloudwatch_log_group": "CLOUDWATCH",
            "aws_cloudwatch_metric_alarm": "CLOUDWATCH",
            "aws_iam_role": "IAM",
            "aws_iam_policy": "IAM",
            "aws_iam_user": "IAM",
            "aws_instance": "EC2",
            "aws_spot_instance_request": "EC2",
            "aws_cloudfront_distribution": "CLOUDFRONT",
            "aws_nat_gateway": "NAT_GATEWAY",
            "aws_eip": "EIP",
            "aws_s3_bucket_encryption": "S3",
            "aws_s3_bucket_lifecycle_configuration": "S3",
            "aws_s3_bucket_intelligent_tiering_configuration": "S3",
        }

        detected: set[str] = set()
        for b in blocks:
            svc = service_map.get(b["type"])
            if svc and svc not in detected:
                detected.add(svc)
                self.services.append(svc)

        if not detected:
            for token, svc in service_map.items():
                short = token.replace("aws_", "")
                if short in lower or token in lower:
                    if svc not in detected:
                        detected.add(svc)
                        self.services.append(svc)

        if not self.services:
            self.services = ["GENERAL_AWS"]

        # Executar regras de pontuacao
        self._score_sg(text, blocks)
        self._score_s3(text, blocks)
        self._score_rds(text, blocks)
        self._score_cloudtrail(text)
        self._score_config(text)
        self._score_cloudwatch(text)
        self._score_iam(text, blocks)
        self._score_elb(text, blocks)
        self._score_multi_az_ha(text, blocks)
        self._score_finops(text, blocks)

        # Bonus por otimizacoes FinOps (cada uma vale ate 8 pts, max 40)
        finops_bonus = min(40, len(self.optimizations) * 8)
        self.score += finops_bonus

        self.score = max(0, min(100, self.score))

        return {
            "score": self.score,
            "findings": self.findings,
            "optimizations": self.optimizations,
            "services": self.services,
            "category_points": self.category_points,
        }

    # ------------------------------------------------------------------
    # Regras de pontuacao (pontos POSITIVOS)
    # ------------------------------------------------------------------

    def _score_sg(self, text: str, blocks: List[Dict[str, str]]) -> None:
        sgs = [b for b in blocks if b["type"] == "aws_security_group"]
        if not sgs:
            self._add_finding("LOW", "SecurityGroup",
                              "Nenhum Security Group definido",
                              "Defina Security Groups restritos para controlar tráfego.")
            return

        max_points = self.WEIGHT_SG
        points_per_sg = max_points / len(sgs)
        admin_ports = {"22", "3389"}
        # Portas que sao aceitaveis de 0.0.0.0/0 em Load Balancers (public-facing)
        lb_public_ports = {"80", "443"}

        for b in sgs:
            body = b["body"]
            ingress_blocks = self._extract_ingress_blocks(body)

            sg_ingress_ok = True
            for ingress in ingress_blocks:
                if '"0.0.0.0/0"' not in ingress:
                    continue
                ports = re.findall(r"from_port\s*=\s*(\d+)", ingress)
                if not ports:
                    continue

                # Se for porta 80/443 e nao houver porta administrativa, nao penaliza
                # (comum em ALB/ELB public-facing)
                all_lb_ports = all(p in lb_public_ports for p in ports)
                if all_lb_ports:
                    continue

                if any(p in admin_ports for p in ports):
                    sg_ingress_ok = False
                    self._add_finding("HIGH", "SecurityGroup",
                                      "SG '%s' permite 0.0.0.0/0 em porta administrativa (%s)" % (b["name"], ", ".join(ports)),
                                      "Restrinja SSH/RDP a CIDRs específicos ou use Session Manager.")
                else:
                    sg_ingress_ok = False
                    self._add_finding("MEDIUM", "SecurityGroup",
                                      "SG '%s' permite 0.0.0.0/0 nas portas %s" % (b["name"], ", ".join(ports)),
                                      "Restrinja o CIDR de origem ao mínimo necessário.")

            # Egress irrestrito: gera finding LOW mas NÃO tira pontos do SG
            # (egress aberto é comum e menos crítico que ingress aberto)
            if re.search(r'egress\s*\{[^}]*protocol\s*=\s*"-1"[^}]*cidr_blocks\s*=\s*\["0\.0\.0\.0/0"\]', body, re.DOTALL):
                self._add_finding("LOW", "SecurityGroup",
                                  "SG '%s' tem egress irrestrito" % b["name"],
                                  "Considere restringir o tráfego de saída.")

            if sg_ingress_ok:
                self._add_points("SG", int(points_per_sg))

    def _score_s3(self, text: str, blocks: List[Dict[str, str]]) -> None:
        s3_buckets = [b for b in blocks if b["type"] == "aws_s3_bucket"]
        if not s3_buckets:
            return

        max_points = self.WEIGHT_S3
        points_per_bucket = max_points / len(s3_buckets)
        has_public_access_block = self._has_resource_type(text, "aws_s3_bucket_public_access_block")
        has_encryption = self._has_resource_type(text, "aws_s3_bucket_encryption")

        for b in s3_buckets:
            body = b["body"]
            acl = self._get_attr(body, "acl")
            bucket_ok = True

            if acl in ("public-read", "public-read-write", "public-write"):
                bucket_ok = False
                self._add_finding("HIGH", "S3",
                                  "Bucket '%s' tem ACL publica (%s)" % (b["name"], acl),
                                  "Defina acl = 'private'.")

            if not has_encryption:
                bucket_ok = False
                self._add_finding("HIGH", "S3",
                                  "Bucket '%s' nao possui criptografia at rest" % b["name"],
                                  "Adicione aws_s3_bucket_encryption.")

            if bucket_ok:
                self._add_points("S3", int(points_per_bucket))

        if has_public_access_block and s3_buckets:
            self._add_points("S3", int(max_points * 0.25))  # bonus por Block Public Access
        elif s3_buckets and not has_public_access_block:
            self._add_finding("HIGH", "S3",
                              "Nenhum aws_s3_bucket_public_access_block configurado",
                              "Adicione aws_s3_bucket_public_access_block.")

        if self._has_resource_type(text, "aws_s3_bucket_intelligent_tiering_configuration"):
            self.optimizations.append({
                "service": "S3",
                "action": "S3 Intelligent-Tiering habilitado",
                "impact": "Reducao de custos de armazenamento por movimentacao automatica entre niveis.",
            })

        if self._has_resource_type(text, "aws_s3_bucket_lifecycle_configuration"):
            self.optimizations.append({
                "service": "S3",
                "action": "Lifecycle policy para S3 Glacier / Deep Archive",
                "impact": "Arquivamento de longo prazo com reducao de custo.",
            })

    def _score_rds(self, text: str, blocks: List[Dict[str, str]]) -> None:
        rds_instances = [b for b in blocks if b["type"] == "aws_db_instance"]
        if not rds_instances:
            return

        max_points = self.WEIGHT_RDS
        points_per_instance = max_points / len(rds_instances)

        for b in rds_instances:
            body = b["body"]
            instance_ok = True

            encrypted = self._get_bool(body, "storage_encrypted")
            if encrypted is False:
                instance_ok = False
                self._add_finding("HIGH", "RDS",
                                  "RDS '%s' nao possui criptografia at rest" % b["name"],
                                  "Defina storage_encrypted = true.")

            publicly_accessible = self._get_bool(body, "publicly_accessible")
            if publicly_accessible is True:
                instance_ok = False
                self._add_finding("HIGH", "RDS",
                                  "RDS '%s' e publicamente acessivel" % b["name"],
                                  "Defina publicly_accessible = false.")

            multi_az = self._get_bool(body, "multi_az")
            if multi_az is False:
                instance_ok = False
                self._add_finding("MEDIUM", "RDS",
                                  "RDS '%s' nao esta em Multi-AZ" % b["name"],
                                  "Habilite multi_az = true.")

            backup = self._get_attr(body, "backup_retention_period")
            if backup is None or backup == "0":
                instance_ok = False
                self._add_finding("MEDIUM", "RDS",
                                  "RDS '%s' nao possui retençao de backup" % b["name"],
                                  "Defina backup_retention_period >= 7 dias.")

            if instance_ok:
                self._add_points("RDS", int(points_per_instance))

    def _score_cloudtrail(self, text: str) -> None:
        if self._has_resource_type(text, "aws_cloudtrail"):
            self._add_points("CloudTrail", self.WEIGHT_CLOUDTRAIL)
        else:
            self._add_finding("HIGH", "CloudTrail",
                              "Nenhum trail CloudTrail configurado",
                              "Adicione aws_cloudtrail para auditoria de API.")

    def _score_config(self, text: str) -> None:
        if self._has_resource_type(text, "aws_config_configuration_recorder"):
            self._add_points("Config", self.WEIGHT_CONFIG)
        else:
            self._add_finding("MEDIUM", "AWS Config",
                              "AWS Config nao esta habilitado",
                              "Adicione aws_config_configuration_recorder.")

    def _score_cloudwatch(self, text: str) -> None:
        has_compute = (
            self._has_resource_type(text, "aws_instance") or
            self._has_resource_type(text, "aws_db_instance") or
            self._has_resource_type(text, "aws_lb") or
            self._has_resource_type(text, "aws_elb")
        )
        # Se nao ha recursos computacionais, CloudWatch nao e obrigatorio (neutro)
        if not has_compute:
            return

        has_log_group = self._has_resource_type(text, "aws_cloudwatch_log_group")
        has_alarm = self._has_resource_type(text, "aws_cloudwatch_metric_alarm")

        if has_log_group and has_alarm:
            self._add_points("CloudWatch", self.WEIGHT_CLOUDWATCH)
        elif has_log_group or has_alarm:
            self._add_points("CloudWatch", int(self.WEIGHT_CLOUDWATCH * 0.5))
            self._add_finding("LOW", "CloudWatch",
                              "CloudWatch parcialmente configurado",
                              "Adicione tanto log groups quanto alarmes metricos.")
        else:
            self._add_finding("MEDIUM", "CloudWatch",
                              "Nenhum recurso CloudWatch configurado",
                              "Adicione aws_cloudwatch_log_group e aws_cloudwatch_metric_alarm.")

    def _score_iam(self, text: str, blocks: List[Dict[str, str]]) -> None:
        policies = [b for b in blocks if b["type"] == "aws_iam_policy"]
        has_wildcard = False

        for b in policies:
            body = b["body"]
            if '"Action"\s*:\s*"*"' in body or '"Action"\s*:\s*\[\s*"*"' in body:
                has_wildcard = True
                self._add_finding("HIGH", "IAM",
                                  "Policy '%s' usa wildcard (*) em Action" % b["name"],
                                  "Use acoes específicas (princípio do menor privilégio).")
            if '"Resource"\s*:\s*"*"' in body or '"Resource"\s*:\s*\[\s*"*"' in body:
                has_wildcard = True
                self._add_finding("HIGH", "IAM",
                                  "Policy '%s' usa wildcard (*) em Resource" % b["name"],
                                  "Especifique ARNs mínimos necessários.")

        if not has_wildcard:
            self._add_points("IAM", self.WEIGHT_IAM)
        elif policies:
            # Tem policies mas com wildcard - nao ganha pontos
            pass

        # Se nao ha policies IAM definidas, nem penaliza nem premia (neutro)

    def _score_elb(self, text: str, blocks: List[Dict[str, str]]) -> None:
        elbs = [b for b in blocks if b["type"] in ("aws_elb", "aws_lb")]
        if not elbs:
            return

        max_points = self.WEIGHT_ELB
        points_per_elb = max_points / len(elbs)

        for b in elbs:
            body = b["body"]
            elb_ok = True

            if b["type"] == "aws_elb":
                has_http = bool(re.search(r'lb_protocol\s*=\s*"http"', body))
                has_https = bool(re.search(r'lb_protocol\s*=\s*"(https|ssl)"', body))
                if has_http and not has_https:
                    elb_ok = False
                    self._add_finding("HIGH", "ELB",
                                      "ELB '%s' expoe apenas HTTP (sem SSL)" % b["name"],
                                      "Adicione listener HTTPS na porta 443.")

            if b["type"] == "aws_lb":
                has_https_listener = bool(re.search(r'port\s*=\s*"443".*?protocol\s*=\s*"HTTPS"', text, re.DOTALL))
                if not has_https_listener:
                    elb_ok = False
                    self._add_finding("HIGH", "ALB",
                                      "ALB '%s' nao possui listener HTTPS" % b["name"],
                                      "Adicione aws_lb_listener na porta 443 com HTTPS.")

            if elb_ok:
                self._add_points("ELB", int(points_per_elb))

    def _score_multi_az_ha(self, text: str, blocks: List[Dict[str, str]]) -> None:
        subnets = [b for b in blocks if b["type"] == "aws_subnet"]
        azs = set()
        for b in subnets:
            az = self._get_attr(b["body"], "availability_zone")
            if az:
                azs.add(az)

        has_rds = self._has_resource_type(text, "aws_db_instance")
        has_alb = self._has_resource_type(text, "aws_lb") or self._has_resource_type(text, "aws_elb")

        if has_rds and len(azs) >= 2:
            # Bonus pequeno por HA de rede com RDS
            self._add_points("RDS", 2)  # pontos extras ja contados acima
        elif has_rds and len(azs) < 2:
            self._add_finding("MEDIUM", "RDS",
                              "RDS em apenas uma AZ",
                              "Use subnets em duas ou mais AZs com Multi-AZ.")

        if has_alb and len(azs) >= 2:
            self._add_points("ELB", 2)
        elif has_alb and len(azs) < 2:
            self._add_finding("MEDIUM", "ALB",
                              "ALB em apenas uma AZ",
                              "Distribua o ALB em duas ou mais AZs.")

    def _score_finops(self, text: str, blocks: List[Dict[str, str]]) -> None:
        lower = text.lower()

        graviton_patterns = ["t4g", "m7g", "c7g", "r7g", "db.t4g", "cache.t4g", "graviton"]
        has_graviton = any(p in lower for p in graviton_patterns)
        if has_graviton:
            self.optimizations.append({
                "service": "EC2/RDS",
                "action": "Instancias Graviton (ARM64) para custo-beneficio",
                "impact": "Ate 40% melhor preco-performance vs x86.",
            })

        has_spot = self._has_resource_type(text, "aws_spot_instance_request") or "spot" in lower
        if has_spot:
            self.optimizations.append({
                "service": "EC2",
                "action": "Spot Instances para cargas tolerantes a interrupcao",
                "impact": "Ate 90% de economia vs sob demanda.",
            })

        has_cloudfront = self._has_resource_type(text, "aws_cloudfront_distribution")
        if has_cloudfront:
            self.optimizations.append({
                "service": "CloudFront",
                "action": "CDN CloudFront para cache em borda",
                "impact": "Reducao de saida de dados e melhor latencia.",
            })

        if re.search(r'instance_type\s*=\s*"t3\.(micro|small|medium)"', text) and not has_graviton and not has_spot:
            self.optimizations.append({
                "service": "EC2",
                "action": "Migre t3 para Graviton t4g ou use Spot",
                "impact": "Reducao de custo de computacao.",
            })


def analyze_terraform(text: str) -> Dict[str, Any]:
    analyzer = TerraformStaticAnalyzer()
    return analyzer.analyze(text)


def analyze_file(file_path: str) -> Dict[str, Any]:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    return analyze_terraform(content)
