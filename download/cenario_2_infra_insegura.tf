# =============================================================================
# Cenario 2 - Infra Insegura
# Resultado esperado: Score BAIXO
#
# Componentes (problemas de seguranca):
#   - S3 publico (sem Block Public Access)
#   - Security Group aberto 0.0.0.0/0 nas portas 22 (SSH) e 3389 (RDP)
#   - Sem criptografia (S3 e RDS em texto plano)
#   - RDS publico (acessivel pela internet)
#   - Sem CloudTrail (sem auditoria)
#   - IAM com wildcard (*) - permissoes totais
# =============================================================================

provider "aws" {
  region = "us-east-1"
}

# -----------------------------------------------------------------------------
# VPC
# -----------------------------------------------------------------------------
resource "aws_vpc" "insegura" {
  cidr_block       = "10.10.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = {
    Name        = "vpc-insegura"
    Cenario     = "2_infra_insegura"
    Score       = "baixo"
  }
}

# -----------------------------------------------------------------------------
# Subnet publica (RDS exposto)
# -----------------------------------------------------------------------------
resource "aws_subnet" "publica" {
  vpc_id                  = aws_vpc.insegura.id
  cidr_block              = "10.10.1.0/24"
  availability_zone       = "us-east-1a"
  map_public_ip_on_launch = true
  tags = {
    Name        = "subnet-publica"
    Cenario     = "2_infra_insegura"
  }
}

# -----------------------------------------------------------------------------
# Security Group aberto - 0.0.0.0/0 nas portas 22 e 3389
# -----------------------------------------------------------------------------
resource "aws_security_group" "sg_aberto" {
  name        = "sg-aberto"
  description = "SG inseguro: 0.0.0.0/0 aberto nas portas 22 e 3389"
  vpc_id      = aws_vpc.insegura.id

  ingress {
    description = "SSH aberto para todo mundo"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "RDP aberto para todo mundo"
    from_port   = 3389
    to_port     = 3389
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Todos trafegos de entrada"
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Saida irrestrita"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "sg-aberto"
    Cenario     = "2_infra_insegura"
  }
}

# -----------------------------------------------------------------------------
# S3 publico (sem criptografia, sem Block Public Access)
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "publico" {
  bucket = "bucket-publico-cenario2"
  acl    = "public-read"
  tags = {
    Name        = "s3-publico"
    Cenario     = "2_infra_insegura"
  }
}

resource "aws_s3_bucket_policy" "publico_policy" {
  bucket = aws_s3_bucket.publico.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.publico.arn}/*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# RDS publico (sem criptografia, acessivel pela internet)
# -----------------------------------------------------------------------------
resource "aws_db_instance" "rds_inseguro" {
  identifier            = "rds-inseguro-cenario2"
  engine                = "mysql"
  engine_version        = "5.7"
  instance_class        = "db.t3.micro"
  allocated_storage     = 20
  storage_encrypted     = false
  multi_az              = false
  publicly_accessible   = true
  backup_retention_period = 0
  skip_final_snapshot   = true
  tags = {
    Name        = "rds-inseguro"
    Cenario     = "2_infra_insegura"
  }
}

# -----------------------------------------------------------------------------
# Sem CloudTrail - ausencia proposital de auditoria
# -----------------------------------------------------------------------------
# (nao provisionado propositalmente para gerar score baixo)

# -----------------------------------------------------------------------------
# IAM com wildcard (*) - permissoes totais
# -----------------------------------------------------------------------------
resource "aws_iam_user" "wildcard_user" {
  name = "usuario-wildcard-cenario2"
  tags = {
    Name        = "iam-wildcard"
    Cenario     = "2_infra_insegura"
  }
}

resource "aws_iam_policy" "wildcard_policy" {
  name        = "policy-wildcard-cenario2"
  description = "Politica IAM com wildcard - permissoes totais (inseguro)"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "*"
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_user_policy_attachment" "wildcard_attach" {
  user       = aws_iam_user.wildcard_user.name
  policy_arn = aws_iam_policy.wildcard_policy.arn
}

output "score_esperado" {
  value = "BAIXO"
}