import argparse
import os
import sys
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.aws.bedrock import BedrockService
from src.aws.storage import StorageService
from src.rag.store import VectorStore
from src.agents.graph import create_arch_iq_graph


def main():
    parser = argparse.ArgumentParser(prog="arch-iq", description="ArchIQ Cloud Architecture Auditor")
    parser.add_argument("--file", "-f", type=str, help="Path to Terraform or CloudFormation file")
    parser.add_argument("--interactive", "-i", action="store_true", help="Launch interactive architecture copilot")
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
        print("\n" + "=" * 60)
        print(result.get("final_report", ""))
        print("=" * 60)
        return

    print("ArchIQ Interactive Copilot")
    print("Type your cloud architecture design or Terraform snippet below.")
    print("Type 'exit' to quit.\n")

    session_id = str(uuid.uuid4())
    while True:
        try:
            user_input = input("ArchIQ > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "q"]:
                break

            result = graph.invoke({"session_id": session_id, "raw_input": user_input})
            print("\n" + result.get("final_report", ""))
            if result.get("remediated_iac"):
                print("Suggested Remediation:\n" + result.get("remediated_iac", ""))
            print("-" * 50)
        except (KeyboardInterrupt, EOFError):
            break


if __name__ == "__main__":
    main()

