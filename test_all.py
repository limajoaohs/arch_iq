import sys
sys.path.insert(0, '.')
from src.aws.bedrock import BedrockService
from src.aws.storage import StorageService
from src.rag.store import VectorStore
from src.agents.graph import create_arch_iq_graph
from src.agents.nodes import AgentNodes
from src.rag.retriever import KnowledgeRetriever

bedrock = BedrockService()
storage = StorageService()
vector_store = VectorStore(persist_directory='./chroma_data')
data_path = 'data/well_architected.json'
vector_store.seed_data(data_path)
graph = create_arch_iq_graph(vector_store, bedrock, storage)

def run_test(name, test_input):
    print(f"=== {name} ===")
    state = {'session_id': 'test', 'raw_input': test_input}
    final_state = graph.invoke(state)
    audit = final_state.get('security_audit', {})
    findings = audit.get('findings', []) if audit else []
    print(f"  Score: {final_state.get('score')}")
    print(f"  Services: {final_state.get('parsed_services')}")
    print(f"  Findings: {findings}")
    print()

# Teste 1: Apenas EC2 (sem SG) - já testado antes, confirma a correção
run_test("TESTE 1: Apenas EC2", 'resource "aws_instance" "app" { instance_type = "t3.medium" }')

# Teste 2: EC2 + Security Group (com SG) - deve manter o finding
run_test("TESTE 2: EC2 + Security Group", 'resource "aws_instance" "app" { instance_type = "t3.medium" } resource "aws_security_group" "web" { ingress { from_port = 22 to_port = 22 protocol = "tcp" cidr_blocks = ["0.0.0.0/0"] } }')

# Teste 3: RDS sem Multi-AZ
run_test("TESTE 3: RDS sem Multi-AZ", 'resource "aws_db_instance" "prod" { engine = "postgres" instance_class = "db.t3.medium" multi_az = false }')

# Teste 4: VPC + Subnets + EC2
run_test("TESTE 4: VPC + Subnets + EC2", 'resource "aws_vpc" "principal" { cidr_block = "10.0.0.0/16" } resource "aws_subnet" "publica" { vpc_id = aws_vpc.principal.id cidr_block = "10.1.0.0/24" } resource "aws_ec2_instance" "web" { instance_type = "t3.large" subnet_id = aws_subnet.publica.id }')

# Teste 5: S3 sozinho (já testado antes - deve manter o finding de S3)
run_test("TESTE 5: S3 sozinho", 'resource "aws_s3_bucket" "logs" { bucket_name = "meu-logs" block_public_acls = true versioning { enabled = true } }')

# Teste 6: ASG + ALB
run_test("TESTE 6: ASG + ALB", 'resource "aws_autoscaling_group" "web" { name = "asg-web" min_size = 2 max_size = 4 desired_capacity = 2 vpc_zone_identifier = ["subnet-01" "subnet-02"] } resource "aws_lb" "app" { name = "app-lb" internal = false load_balancer_type = "application" subnets = ["subnet-01" "subnet-02"] }')

# Teste 7: Tudo junto
run_test("TESTE 7: Tudo junto", 'resource "aws_vpc" "principal" { cidr_block = "10.0.0.0/16" } resource "aws_subnet" "publica" { vpc_id = aws_vpc.principal.id cidr_block = "10.1.0.0/24" } resource "aws_instance" "app" { instance_type = "t3.medium" } resource "aws_security_group" "web" { ingress { from_port = 22 to_port = 22 protocol = "tcp" cidr_blocks = ["0.0.0.0/0"] } } resource "aws_s3_bucket" "logs" { bucket_name = "logs" block_public_acls = true }')