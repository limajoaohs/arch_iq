resource "aws_security_group" "web_sg" {
  name        = "web-sg"
  description = "Allow inbound SSH"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_s3_bucket" "app_data" {
  bucket = "my-public-company-data-bucket"
}

resource "aws_instance" "app_server" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.large"
}

