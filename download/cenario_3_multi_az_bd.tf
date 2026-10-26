# =============================================================================
# Cenario 3 - Multi-AZ com Banco de Dados
# Resultado esperado: Score MEDIO-ALTO
#
# Componentes:
#   - VPC com subnets privadas e publicas
#   - RDS Multi-AZ (alta disponibilidade)
#   - ElastiCache (Redis/Memcached) em subnets privadas
#   - ALB (Application Load Balancer) frente às instancias
#   - NAT Gateway para saida das subnets privadas
#   - Bastiao (SSH Jump host) para acesso administrativo
#   - CloudWatch (monitoramento de metricas e alarmes)
# =============================================================================

provider "aws" {
  region = "us-east-1"
}

# -----------------------------------------------------------------------------
# VPC
# -----------------------------------------------------------------------------
resource "aws_vpc" "multiaz" {
  cidr_block                           = "10.100.0.0/16"
  enable_dns_hostnames                 = true
  enable_dns_support                   = true
  tags = {
    Name        = "vpc-multiaz"
    Cenario     = "3_multi_az_bd"
    Score       = "medio-alto"
  }
}

# -----------------------------------------------------------------------------
# Subnets publicas (ALB, NAT Gateway)
# -----------------------------------------------------------------------------
resource "aws_subnet" "publica_a" {
  vpc_id                  = aws_vpc.multiaz.id
  cidr_block              = "10.100.1.0/24"
  availability_zone       = "us-east-1a"
  map_public_ip_on_launch = true
  tags = {
    Name        = "subnet-publica-a"
    Cenario     = "3_multi_az_bd"
  }
}

resource "aws_subnet" "publica_b" {
  vpc_id                  = aws_vpc.multiaz.id
  cidr_block              = "10.100.2.0/24"
  availability_zone       = "us-east-1b"
  map_public_ip_on_launch = true
  tags = {
    Name        = "subnet-publica-b"
    Cenario     = "3_multi_az_bd"
  }
}

# -----------------------------------------------------------------------------
# Subnets privadas (RDS, ElastiCache, instancias)
# -----------------------------------------------------------------------------
resource "aws_subnet" "privada_a" {
  vpc_id                  = aws_vpc.multiaz.id
  cidr_block              = "10.100.3.0/24"
  availability_zone       = "us-east-1a"
  map_public_ip_on_launch = false
  tags = {
    Name        = "subnet-privada-a"
    Cenario     = "3_multi_az_bd"
  }
}

resource "aws_subnet" "privada_b" {
  vpc_id                  = aws_vpc.multiaz.id
  cidr_block              = "10.100.4.0/24"
  availability_zone       = "us-east-1b"
  map_public_ip_on_launch = false
  tags = {
    Name        = "subnet-privada-b"
    Cenario     = "3_multi_az_bd"
  }
}

# -----------------------------------------------------------------------------
# Internet Gateway e rotas publicas
# -----------------------------------------------------------------------------
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.multiaz.id
  tags = {
    Name = "igw-multiaz"
  }
}

resource "aws_route_table" "publica" {
  vpc_id = aws_vpc.multiaz.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = {
    Name = "rt-publica"
  }
}

resource "aws_route_table_association" "publica_a" {
  subnet_id      = aws_subnet.publica_a.id
  route_table_id = aws_route_table.publica.id
}

resource "aws_route_table_association" "publica_b" {
  subnet_id      = aws_subnet.publica_b.id
  route_table_id = aws_route_table.publica.id
}

# -----------------------------------------------------------------------------
# NAT Gateway e Elastic IP (saida das subnets privadas)
# -----------------------------------------------------------------------------
resource "aws_eip" "nat" {
  domain = "vpc"
  tags = {
    Name = "eip-nat"
  }
}

resource "aws_nat_gateway" "nat" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.publica_a.id
  tags = {
    Name = "nat-gateway"
  }
}

resource "aws_route_table" "privada" {
  vpc_id = aws_vpc.multiaz.id

  route {
    cidr_block = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat.id
  }

  tags = {
    Name = "rt-privada"
  }
}

resource "aws_route_table_association" "privada_a" {
  subnet_id      = aws_subnet.privada_a.id
  route_table_id = aws_route_table.privada.id
}

resource "aws_route_table_association" "privada_b" {
  subnet_id      = aws_subnet.privada_b.id
  route_table_id = aws_route_table.privada.id
}

# -----------------------------------------------------------------------------
# Security Groups
# -----------------------------------------------------------------------------
resource "aws_security_group" "sg_alb" {
  name        = "sg-alb"
  description = "SG do ALB: porta 80 e 443 abertas"
  vpc_id      = aws_vpc.multiaz.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
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
    Name = "sg-alb"
  }
}

resource "aws_security_group" "sg_app" {
  name        = "sg-app"
  description = "SG das instancias: apenas do ALB na porta 8080"
  vpc_id      = aws_vpc.multiaz.id

  ingress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.sg_alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "sg-app"
  }
}

resource "aws_security_group" "sg_bastiao" {
  name        = "sg-bastiao"
  description = "SG do bastiao: SSH apenas de IP corporativo"
  vpc_id      = aws_vpc.multiaz.id

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
    Name = "sg-bastiao"
  }
}

resource "aws_security_group" "sg_rds" {
  name        = "sg-rds"
  description = "SG do RDS: apenas do SG app na porta 5432"
  vpc_id      = aws_vpc.multiaz.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.sg_app.id]
  }

  tags = {
    Name = "sg-rds"
  }
}

# -----------------------------------------------------------------------------
# Bastiao (SSH Jump host) para acesso administrativo
# -----------------------------------------------------------------------------
resource "aws_instance" "bastiao" {
  ami                    = "ami-0c55b159cbfafe1f0"
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.publica_a.id
  vpc_security_group_ids = [aws_security_group.sg_bastiao.id]
  key_name               = "bastiao-key"
  tags = {
    Name        = "bastiao"
    Cenario     = "3_multi_az_bd"
  }
}

# -----------------------------------------------------------------------------
# ALB (Application Load Balancer) frente às instancias
# -----------------------------------------------------------------------------
resource "aws_lb" "alb" {
  name               = "alb-multiaz"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.sg_alb.id]
  subnets            = [aws_subnet.publica_a.id, aws_subnet.publica_b.id]
  enable_deletion_protection = false

  tags = {
    Name = "alb-multiaz"
  }
}

resource "aws_lb_target_group" "app_tg" {
  name     = "tg-app"
  port     = 8080
  protocol = "HTTP"
  vpc_id   = aws_vpc.multiaz.id

  health_check {
    path = "/health"
    port = "8080"
  }

  tags = {
    Name = "tg-app"
  }
}

resource "aws_lb_listener" "alb_http" {
  load_balancer_arn = aws_lb.alb.id
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app_tg.arn
  }
}

# -----------------------------------------------------------------------------
# RDS Multi-AZ (alta disponibilidade)
# -----------------------------------------------------------------------------
resource "aws_db_subnet_group" "rds_subnet" {
  name       = "rds-subnet-group"
  subnet_ids = [aws_subnet.privada_a.id, aws_subnet.privada_b.id]
  tags = {
    Name = "rds-subnet-group"
  }
}

resource "aws_db_instance" "rds_multi_az" {
  identifier            = "rds-multiaz-cenario3"
  engine                = "postgres"
  engine_version        = "15.4"
  instance_class        = "db.t3.micro"
  allocated_storage     = 20
  db_subnet_group_name  = aws_db_subnet_group.rds_subnet.name
  vpc_security_group_ids = [aws_security_group.sg_rds.id]
  multi_az              = true
  backup_retention_period = 7
  skip_final_snapshot   = false
  tags = {
    Name        = "rds-multiaz"
    Cenario     = "3_multi_az_bd"
  }
}

# -----------------------------------------------------------------------------
# ElastiCache (Redis) em subnets privadas
# -----------------------------------------------------------------------------
resource "aws_elasticache_subnet_group" "cache_subnet" {
  name       = "cache-subnet-group"
  subnet_ids = [aws_subnet.privada_a.id, aws_subnet.privada_b.id]
  tags = {
    Name = "cache-subnet-group"
  }
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id          = "redis-cache-cenario3"
  replication_group_description = "Cache Redis Multi-AZ"
  node_type                     = "cache.t3.micro"
  automatic_failover_enabled    = true
  subnet_group_name             = aws_elasticache_subnet_group.cache_subnet.name
  security_group_ids            = [aws_security_group.sg_app.id]
  tags = {
    Name = "redis-cache"
    Cenario = "3_multi_az_bd"
  }
}

# -----------------------------------------------------------------------------
# CloudWatch (monitoramento de metricas e alarmes)
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "app_logs" {
  name              = "/aws/ec2/app-multiaz"
  retention_in_days = 30
  tags = {
    Name = "cloudwatch-logs"
  }
}

resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "cpu-high-cenario3"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "Alarme de CPU alta nas instancias"
  tags = {
    Name = "cloudwatch-alarme-cpu"
  }
}

output "score_esperado" {
  value = "MEDIO-ALTO"
}