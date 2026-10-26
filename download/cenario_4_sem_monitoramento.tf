# =============================================================================
# Cenario 4 - Sem Monitoramento
# Resultado esperado: Score MEDIO-BAIXO
#
# Problemas (ausencias propositais):
#   - Sem CloudTrail (sem auditoria de API)
#   - Sem AWS Config (sem monitoramento de compliance)
#   - Sem CloudWatch (sem metricas e alarmes)
#   - Sem backup S3 (sem bucket de backup / versionamento desabilitado)
#   - Sem SSL no ELB (Load Balancer apenas HTTP)
# =============================================================================

provider "aws" {
  region = "us-east-1"
}

# -----------------------------------------------------------------------------
# VPC
# -----------------------------------------------------------------------------
resource "aws_vpc" "sem_monitoramento" {
  cidr_block       = "10.200.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = {
    Name        = "vpc-sem-monitoramento"
    Cenario     = "4_sem_monitoramento"
    Score       = "medio-baixo"
  }
}

# -----------------------------------------------------------------------------
# Subnet publica
# -----------------------------------------------------------------------------
resource "aws_subnet" "publica" {
  vpc_id                  = aws_vpc.sem_monitoramento.id
  cidr_block              = "10.200.1.0/24"
  availability_zone       = "us-east-1a"
  map_public_ip_on_launch = true
  tags = {
    Name        = "subnet-publica"
    Cenario     = "4_sem_monitoramento"
  }
}

# -----------------------------------------------------------------------------
# Internet Gateway
# -----------------------------------------------------------------------------
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.sem_monitoramento.id
  tags = {
    Name = "igw-sem-monitoramento"
  }
}

resource "aws_route_table" "publica" {
  vpc_id = aws_vpc.sem_monitoramento.id

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
# Security Group do ELB (aberto)
# -----------------------------------------------------------------------------
resource "aws_security_group" "sg_elb" {
  name        = "sg-elb-sem-ssl"
  description = "SG do ELB sem SSL: porta 80 aberta"
  vpc_id      = aws_vpc.sem_monitoramento.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "sg-elb-sem-ssl"
  }
}

# -----------------------------------------------------------------------------
# ELB (Classic Load Balancer) SEM SSL - apenas HTTP (problema)
# -----------------------------------------------------------------------------
resource "aws_elb" "sem_ssl" {
  name               = "elb-sem-ssl-cenario4"
  availability_zones = ["us-east-1a"]
  security_groups    = [aws_security_group.sg_elb.id]

  listener {
    instance_port     = 80
    instance_protocol = "http"
    lb_port           = 80
    lb_protocol       = "http"
    # SEM listener SSL/HTTPS - ausencia proposital
  }

  instances = []

  tags = {
    Name        = "elb-sem-ssl"
    Cenario     = "4_sem_monitoramento"
  }
}

# -----------------------------------------------------------------------------
# Instancia EC2 (sem CloudWatch detailed monitoring)
# -----------------------------------------------------------------------------
resource "aws_instance" "app" {
  ami                    = "ami-0c55b159cbfafe1f0"
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.publica.id
  vpc_security_group_ids = [aws_security_group.sg_elb.id]
  monitoring             = false  # Sem monitoramento detalhado CloudWatch
  tags = {
    Name        = "app-sem-monitoramento"
    Cenario     = "4_sem_monitoramento"
  }
}

# -----------------------------------------------------------------------------
# S3 SEM backup / sem versionamento / sem criptografia (problema)
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "sem_backup" {
  bucket = "bucket-sem-backup-cenario4"
  acl    = "private"
  tags = {
    Name        = "s3-sem-backup"
    Cenario     = "4_sem_monitoramento"
  }
}

# Nenhum versionamento, nenhuma regra de lifecycle, nenhuma criptografia
# ausencia proposital para gerar score medio-baixo

# -----------------------------------------------------------------------------
# Ausencias propositais (nao provisionadas):
#   - Sem CloudTrail (auditoria de API ausente)
#   - Sem AWS Config (compliance ausente)
#   - Sem CloudWatch alarms / log groups (monitoramento ausente)
# =============================================================================

output "score_esperado" {
  value = "MEDIO-BAIXO"
}