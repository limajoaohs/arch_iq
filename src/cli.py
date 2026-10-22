import argparse
import os
import sys
import uuid
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.aws.bedrock import BedrockService
from src.aws.storage import StorageService
from src.rag.store import VectorStore
from src.agents.graph import create_arch_iq_graph


def print_summary_cards(result):
    """Print summary cards at the top of the report."""
    score = result.get("score", 0)
    fin_audit = result.get("finops_audit", {})
    savings = fin_audit.get("monthly_savings_pct", 0)
    services = result.get("parsed_services", [])

    # Determine score status level
    if score >= 90:
        score_status = "EXCELENTE"
    elif score >= 75:
        score_status = "BOA"
    elif score >= 50:
        score_status = "REGULAR"
    else:
        score_status = "ATENCAO"

    # Determine savings level
    if savings >= 30:
        savings_level = "OTIMO"
    elif savings >= 15:
        savings_level = "BOM"
    elif savings >= 5:
        savings_level = "MODERADO"
    else:
        savings_level = "BAIXO"

    print("=" * 70)
    print(" ARCHIQ RESUMO EXECUTIVO")
    print("=" * 70)
    print(f" Pontuacao de adesao: {score} / 100  [{score_status}]")
    print(f" Poupança mensal potencial: {savings}%  [{savings_level}]")
    print(f" Servicos detectados: {', '.join(services) if services else 'nenhum'}")
    print()
    print(" Principais findings de seguranca:")
    sec_audit = result.get("security_audit", {})
    for f in sec_audit.get("findings", [])[:3]:
        sev = f.get("severity", "INFO")
        svc = f.get("service", "")
        rule = f.get("rule", "")
        print(f"   - [{sev}] {svc}: {rule}")
    if len(sec_audit.get("findings", [])) > 3:
        print(f"   ... e mais {len(sec_audit['findings']) - 3} findings")
    print()
    print(" Recomendacoes de otimizacao de custos:")
    for o in fin_audit.get("optimizations", [])[:3]:
        svc = o.get("service", "")
        action = o.get("action", "")
        print(f"   - {svc}: {action}")
    if len(fin_audit.get("optimizations", [])) > 3:
        print(f"   ... e mais {len(fin_audit['optimizations']) - 3} recomendacoes")
    print("=" * 70)
    print()


def print_commands():
    print("Comandos disponiveis:")
    print("  help  - Mostra esta mensagem")
    print("  exit  / quit  / q  - Sai do programa")
    print("  resumo - Mostra resumo executivo (ja incluso)")
    print("  followup - Mais detalhes sobre findings")
    print("  wizard - Fluxo guiado passo a passo")
    print()


def generate_follow_ups(result):
    """Generate smart follow-up questions based on the analysis results."""
    follow_ups = []
    sec = result.get("security_audit", {})
    fin = result.get("finops_audit", {})
    score = result.get("score", 0)

    # If there are high severity findings
    high_findings = [f for f in sec.get("findings", []) if f.get("severity") == "HIGH"]
    if high_findings:
        follow_ups.append("mais detalhes sobre os findings de alto risco")

    # If there are cost savings opportunities
    savings = fin.get("monthly_savings_pct", 0)
    if savings and savings >= 10:
        follow_ups.append("como implementar as recomendacoes de economia")

    # If score is low, suggest improvement plan
    if score < 70:
        follow_ups.append("um plano de melhoria passo a passo")

    # If specific services were detected
    services = result.get("parsed_services", [])
    if "S3" in services:
        follow_ups.append("configuracao otimizada de buckets S3")
    if "EC2" in services:
        follow_ups.append("diretrizes de instancia EC2 de baixo custo")

    return follow_ups[:3]  # Limit to 3 suggestions


def run_wizard(graph, storage_service, session_id: str):
    """Run a guided wizard workflow for architecture analysis."""
    print("=" * 60)
    print(" ARCHIQ FLUXO GUIDE - PASSO A PASSO")
    print("=" * 60)
    print()
    print("Vou fazer algumas perguntas sobre sua arquitetura e depois gerar o relatorio.")
    print()

    # Step 1: Services detected
    print("Passo 1: Quais serviços AWS voce usa? (digite os nomes ou números)")
    print("  1. S3")
    print("  2. EC2")
    print("  3. RDS")
    print("  4. VPC")
    print("  5. IAM")
    print("  6. Lambda")
    print("  7. DynamoDB")
    print("  8. Mais algum (descreva): ")
    svc_input = input(">>> ").strip().lower()

    service_keywords = {
        "s3": "S3", "ec2": "EC2", "rds": "RDS", "vpc": "VPC",
        "iam": "IAM", "lambda": "LAMBDA", "dynamodb": "DYNAMODB"
    }

    detected_services = []
    if svc_input:
        for keyword, svc_name in service_keywords.items():
            if keyword in svc_input:
                detected_services.append(svc_name)

    if not detected_services:
        print("Nao consegui detectar servicos automaticamente.")
        print("Por favor, descreva Briefly sua arquitetura:")
        desc = input(">>> ").strip()
        detected_services = ["GENERAL_AWS"]
    else:
        print(f"Servicos detectados: {', '.join(detected_services)}\n")

    # Step 2: Main concern
    print("Passo 2: Qual e sua principal preocupacao?")
    print("  1. Seguranca")
    print("  2. Otimizacao de custos")
    print("  3. Desempenho")
    print("  4. Confiabilidade")
    concern_input = input(">>> ").strip()
    concern_map = {"1": "security", "2": "cost", "3": "performance", "4": "reliability"}
    concern = concern_map.get(concern_input, "security")

    # Step 3: Input architecture
    print("Passo 3: Agora descreva sua arquitetura ou envie codigo Terraform:")
    print("(Ou digite 'pular' se quiser usar entrada livre)")
    arch_input = input(">>> ").strip()

    if arch_input.lower() == "pular":
        arch_input = f"Arquitetura com {', '.join(detected_services)}"

    # Show processing indicator
    print("ArchIQ > Processando sua arquitetura, por favor aguarde...", end=" ", flush=True)
    start_time = time.time()

    result = graph.invoke({
        "session_id": session_id,
        "raw_input": arch_input
    })
    elapsed = time.time() - start_time

    # Clear line
    print("\r" + " " * 60 + "\r", end="")

    # Print summary cards
    print_summary_cards(result)
    print("\n" + result.get("final_report", ""))
    print(f"Tempo de processamento: {elapsed:.1f}s")
    print("-" * 60)

    # Follow-ups
    follow_ups = generate_follow_ups(result)
    if follow_ups:
        print()
        print("Interesses relacionados:")
        for i, suggestion in enumerate(follow_ups, 1):
            print(f"  {i}. {suggestion}")
        print("  0. Nenhuma das above")
        print()

    return result


def main():
    parser = argparse.ArgumentParser(prog="arch-iq", description="ArchIQ Cloud Architecture Auditor")
    parser.add_argument("--file", "-f", type=str, help="Path to Terraform or CloudFormation file")
    parser.add_argument("--interactive", "-i", action="store_true", help="Launch interactive architecture copilot")
    parser.add_argument("--wizard", "-w", action="store_true", help="Launch guided architecture wizard")
    args = parser.parse_args()

    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "well_architected.json")
    vector_store = VectorStore()
    vector_store.seed_data(os.path.abspath(data_path))

    bedrock_service = BedrockService()
    storage_service = StorageService()
    graph = create_arch_iq_graph(vector_store, bedrock_service, storage_service)

    if args.file:
        if not os.path.exists(args.file):
            print(f"Error: File '{args.file}' not found.")
            sys.exit(1)

        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()

        session_id = str(uuid.uuid4())
        print(f"Auditing file {args.file} with ArchIQ...")
        result = graph.invoke({"session_id": session_id, "raw_input": content})
        print_summary_cards(result)
        print("\n" + result.get("final_report", ""))
        print("=" * 70)
        if result.get("remediated_iac"):
            print("\nSugestao de remediacao:\n" + result.get("remediated_iac", ""))
        return

    if args.wizard:
        session_id = str(uuid.uuid4())
        run_wizard(graph, storage_service, session_id)
        return

    print("Arquitetura em nuvem - Copilho ArchIQ")
    print("=" * 50)
    print("Eu analiso sua arquitetura e gero um relatorio de seguranca e custos.")
    print("Digite 'help' para ver comandos disponiveis ou 'exit' para sair.\n")

    session_id = str(uuid.uuid4())
    while True:
        try:
            user_input = input("Voce > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "q"]:
                print("Até mais! Obrigado por usar o ArchIQ.")
                break
            if user_input.lower() == "help":
                print_commands()
                continue
            if user_input.lower() == "resumo":
                print("Resumo ja incluso nos resultados acima.\n")
                continue
            if user_input.lower() == "wizard":
                run_wizard(graph, storage_service, session_id)
                continue

            # Show processing indicator
            print("ArchIQ > Analisando sua arquitetura, por favor aguarde...", end=" ", flush=True)

            start_time = time.time()
            result = graph.invoke({"session_id": session_id, "raw_input": user_input})
            elapsed = time.time() - start_time

            # Clear the "analyzing" line
            print("\r" + " " * 60 + "\r", end="")

            print_summary_cards(result)
            print("\n" + result.get("final_report", ""))
            print(f"Tempo de processamento: {elapsed:.1f}s")
            print("-" * 50)

            # Smart follow-up suggestions
            follow_ups = generate_follow_ups(result)
            if follow_ups:
                print()
                print("Voce tambem gostaria de saber:")
                for i, suggestion in enumerate(follow_ups, 1):
                    print(f"  {i}. {suggestion}")
                print("  0. Nenhuma das acima")
                print()

        except (KeyboardInterrupt, EOFError):
            print("\nAté mais! Obrigado por usar o ArchIQ.")
            break


if __name__ == "__main__":
    main()