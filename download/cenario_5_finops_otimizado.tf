# =============================================================================
# Cenario 5 - FinOps Otimizado
# Resultado esperado: Score ALTO + FinOps
#
# Componentes (otimizacao de custos / FinOps):
#   - Graviton2 (instances ARM64 - melhor custo-beneficio)
#   - S3 Intelligent-Tiering (movimentacao automatica entre niveis)
#   - RDS Graviton (instancia ARM64 para banco)
#   - Spot Instances (EC2 spot para cargas nao criticas)
#   - S3 Glacier (arquivamento de longo prazo, baixo custo)
#   - CloudFront (CDN - reducao de saida de dados / origin shield)
# =============================================================================

provider "aws" {
  region = "us-east-1"
}

# -----------------------------------------------------------------------------
# VPC
# -----------------------------------------------------------------------------
resource "aws_vpc" "finops" {
  cidr_block                           = "10.300.0.0/16"
  enable_dns_hostnames                 = true
  enable_dns_support                   = true
  tags = {
    Name        = "vpc-finops"
    Cenario     = "5_finops_otimizado"
    Score       = "alto-finops"
  }
}

# -----------------------------------------------------------------------------
# Subnet publica
# -----------------------------------------------------------------------------
resource "aws_subnet" "publica" {
  vpc_id                  = aws_vpc.finops.id
  cidr_block              = "10.300.1.0/24"
  availability_zone       = "us-east-1a"
  map_public_ip_on_launch = true
  tags = {
    Name        = "subnet-publica"
    Cenario     = "5_finops_otimizado"
  }
}

# -----------------------------------------------------------------------------
# Internet Gateway
# -----------------------------------------------------------------------------
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.finops.id
  tags = {
    Name = "igw-finops"
  }
}

resource "aws_route_table" "publica" {
  vpc_id = aws_vpc.finops.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = {
    Name = "rt-publica"
  }
}

resource "aws_route_table_association" "publica" {
  subnet_id      = aws_subnet.publica.id
  route_table_id = aws_route_table.publica.id
}

# -----------------------------------------------------------------------------
# Security Group (HTTP/HTTPS + SSH restrito)
# -----------------------------------------------------------------------------
resource "aws_security_group" "sg_app" {
  name        = "sg-app-finops"
  description = "SG para instancias otimizadas por custo"
  vpc_id      = aws_vpc.finops.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "sg-app-finops"
  }
}

# -----------------------------------------------------------------------------
# Spot Instances (EC2 Spot - economia de custo para cargas nao criticas)
# -----------------------------------------------------------------------------
resource "aws_spot_instance_request" "spot_worker" {
  spot_price       = "0.05"
  instance_type    = "t3.micro"
  ami              = "ami-0c55b159cbfafe1f0"
  subnet_id        = aws_subnet.publica.id
  vpc_security_group_ids = [aws_security_group.sg_app.id]
  instance_interruption_behavior = "terminate"
  tags = {
    Name        = "spot-worker"
    Cenario     = "5_finops_otimizado"
  }
}

# -----------------------------------------------------------------------------
# Instancia Graviton2 (ARM64 - melhor custo-beneficio)
# -----------------------------------------------------------------------------
resource "aws_instance" "graviton2" {
  ami                    = "ami-0c55b159cbfafe1f0"
  instance_type          = "t4g.micro"   # Graviton2 (ARM64)
  subnet_id              = aws_subnet.publica.id
  vpc_security_group_ids = [aws_security_group.sg_app.id]
  tags = {
    Name        = "graviton2-worker"
    Cenario     = "5_finops_otimizado"
    Arquitetura = "ARM64-Graviton2"
  }
}

# -----------------------------------------------------------------------------
# RDS Graviton (instancia ARM64 para banco - otimizacao FinOps)
# -----------------------------------------------------------------------------
resource "aws_db_instance" "rds_graviton" {
  identifier            = "rds-graviton-cenario5"
  engine                = "postgres"
  engine_version        = "15.4"
  instance_class        = "db.t4g.micro"   # Graviton (ARM64)
  allocated_storage     = 20
  storage_encrypted     = true
  multi_az              = false
  backup_retention_period = 7
  skip_final_snapshot   = false
  tags = {
    Name        = "rds-graviton"
    Cenario     = "5_finops_otimizado"
    Arquitetura = "ARM64-Graviton"
  }
}

# -----------------------------------------------------------------------------
# S3 Intelligent-Tiering (movimentacao automatica entre niveis de acesso)
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "intelligent_tiering" {
  bucket = "bucket-intelligent-tiering-cenario5"
  tags = {
    Name        = "s3-intelligent-tiering"
    Cenario     = "5_finops_otimizado"
  }
}

resource "aws_s3_bucket_intelligent_tiering_configuration" "tiering" {
  bucket = aws_s3_bucket.intelligent_tiering.id
  name   = "default-tiering"

  status = "Enabled"

  tier {
    access_tier = "ARCHIVE_ACCESS"
    days        = 90
  }

  tier {
    access_tier = "DEEP_ARCHIVE_ACCESS"
    days        = 180
  }
}

# -----------------------------------------------------------------------------
# S3 Glacier (arquivamento de longo prazo via Glacier Instant Retrieval / Flexible Retrieval)
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "glacier" {
  bucket = "bucket-glacier-cenario5"
  tags = {
    Name        = "s3-glacier"
    Cenario     = "5_finops_otimizado"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "glacier_lifecycle" {
  bucket = aws_s3_bucket.glacier.id

  rule {
    id     = "mover-para-glacier"
    status = "Enabled"

    filter {
      prefix = "arquivo/"
    }

    transition {
      days          = 30
      storage_class = "GLACIER_IR"  # Glacier Instant Retrieval
    }

    transition {
      days          = 90
      storage_class = "DEEP_ARCHIVE"  # Glacier Deep Archive (maior economia)
    }
  }
}

# -----------------------------------------------------------------------------
# CloudFront (CDN - reducao de saida de dados, cache em borda, origin shield)
# -----------------------------------------------------------------------------
resource "aws_cloudfront_distribution" "cdn" {
  origin {
    domain_name = aws_s3_bucket.intelligent_tiering.bucket_regional_domain_name
    origin_id   = "S3-intelligent-tiering"

    s3_origin_config {
      origin_access_identity = ""  # simplificado para exemplo
    }
  }

  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"

  default_cache_behavior {
    target_origin_id = "S3-intelligent-tiering"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]

    forwarded_values {
      query_string = false

      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 3600
    max_ttl     = 86400
  }

  price_class = "PriceClass_100"  # apenas USA, Canada, Europa (menor custo)

  tags = {
    Name        = "cloudfront-cdn"
    Cenario     = "5_finops_otimizado"
  }
}

output "score_esperado" {
  value = "ALTO + FINOPS"
}