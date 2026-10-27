from typing import TypedDict, List, Dict, Any, Optional


class ArchIQState(TypedDict, total=False):
    session_id: str
    raw_input: str
    parsed_services: List[str]
    retrieved_knowledge: str
    security_audit: Dict[str, Any]
    finops_audit: Dict[str, Any]
    remediated_iac: str
    final_report: str
    technical_report: str
    layperson_explanation: str
    score: int
    errors: List[str]

