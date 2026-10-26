# =============================================================================
# Cenario 1 - Infra Segura
# Resultado esperado: Score ALTO
#
# Componentes:
#   - VPC com subnets privadas
#   - Security Groups restritos (sem 0.0.0.0/0)
#   - S3 privado (Block Public Access + criptografia)
#   - RDS criptografado (multi-AZ, snapshot criptografado)
#   - CloudTrail (auditoria de API)
#   - AWS Config (monitoramento de compliance)
#   - IAM least privilege (role com permissoes minimas)
# =============================================================================

provider "aws" {
  region = "us-east-1"
}

# -----------------------------------------------------------------------------
# VPC
# -----------------------------------------------------------------------------
resource "aws_vpc" "segura" {
  cidr_block                           = "10.0.0.0/16"
  enable_dns_hostnames                 = true
  enable_dns_support                   = true
  enable_classiclink                   = false
  tags = {
    Name        = "vpc-segura"
    Cenario     = "1_infra_segura"
    Score       = "alto"
  }
}

# -----------------------------------------------------------------------------
# Subnets privadas (sem rota para Internet Gateway)
# -----------------------------------------------------------------------------
resource "aws_subnet" "privada_a" {
  vpc_id                  = aws_vpc.segura.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "us-east-1a"
  map_public_ip_on_launch = false
  tags = {
    Name        = "subnet-privada-a"
    Cenario     = "1_infra_segura"
  }
}

resource "aws_subnet" "privada_b" {
  vpc_id                  = aws_vpc.segura.id
  cidr_block              = "10.0.2.0/24"
  availability_zone       = "us-east-1b"
  map_public_ip_on_launch = false
  tags = {
    Name        = "subnet-privada-b"
    Cenario     = "1_infra_segura"
  }
}

# -----------------------------------------------------------------------------
# Security Group restrito (apenas porta 443 de qualquer IP, SSH apenas de range corporativo)
# -----------------------------------------------------------------------------
resource "aws_security_group" "sg_app_seguro" {
  name        = "sg-app-seguro"
  description = "SG restrito: apenas HTTPS 443 e SSH restrito"
  vpc_id      = aws_vpc.segura.id

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH corporativo"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }

  egress {
    description = "Saida para internet"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "sg-app-seguro"
    Cenario     = "1_infra_segura"
  }
}

# -----------------------------------------------------------------------------
# S3 privado (Block Public Access + criptografia SSE-S3)
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "privado" {
  bucket = "bucket-privado-cenario1"
  tags = {
    Name        = "s3-privado"
    Cenario     = "1_infra_segura"
  }
}

resource "aws_s3_bucket_public_access_block" "privado_block" {
  bucket = aws_s3_bucket.privado.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_encryption" "privado_enc" {
  bucket = aws_s3_bucket.privado.id

  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }
}

# -----------------------------------------------------------------------------
# RDS criptografado (multi-AZ, snapshot criptografado)
# -----------------------------------------------------------------------------
resource "aws_db_instance" "rds_seguro" {
  identifier            = "rds-seguro-cenario1"
  engine                = "postgres"
  engine_version        = "15.4"
  instance_class        = "db.t3.micro"
  allocated_storage     = 20
  storage_encrypted     = true
  multi_az              = true
  backup_retention_period = 7
  skip_final_snapshot   = false
  final_snapshot_identifier = "rds-seguro-final-snap"
  tags = {
    Name        = "rds-seguro"
    Cenario     = "1_infra_segura"
  }
}

# -----------------------------------------------------------------------------
# CloudTrail (auditoria de API)
# -----------------------------------------------------------------------------
resource "aws_cloudtrail" "auditoria" {
  name                          = "cloudtrail-auditoria-cenario1"
  s3_bucket_name                = aws_s3_bucket.privado.id
  enable_logging                = true
  include_global_service_events = true
  is_multi_region_trail         = true
  tags = {
    Name        = "cloudtrail-auditoria"
    Cenario     = "1_infra_segura"
  }
}

# -----------------------------------------------------------------------------
# AWS Config (monitoramento de compliance)
# -----------------------------------------------------------------------------
resource "aws_config_configuration_recorder" "config" {
  name     = "config-recorder-cenario1"
  role_arn = aws_iam_role.config_role.arn
}

resource "aws_config_delivery_channel" "config" {
  name          = "config-delivery-cenario1"
  s3_bucket_name = aws_s3_bucket.privado.id
}

# -----------------------------------------------------------------------------
# IAM least privilege (role com permissoes minimas para Config)
# -----------------------------------------------------------------------------
resource "aws_iam_role" "config_role" {
  name = "config-role-cenario1"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = {
          Service = "config.amazonaws.com"
        }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "config" {
  role       = aws_iam_role.config_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSConfigRole"
}

output "score_esperado" {
  value = "ALTO"
}